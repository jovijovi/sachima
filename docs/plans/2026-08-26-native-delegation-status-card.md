# Sachima Native Delegation Status Card — Implementation Plan

> **Type:** Implementation plan (candidate)
> **Status:** Saved for review; source implementation is not authorized
> **For Hermes:** Execute only after explicit source-implementation approval. Keep ARS as the lifecycle authority and Feishu cards as a fallible presentation projection.

**Goal:** Add one persistent Feishu rich interactive status card per Sachima native delegation Task, updated in place across all continuation rounds without confusing Task identity, Turn identity, ARS Run identity, or Session reuse.

**Architecture:** The card is keyed by the stable Sachima `task_ref` (`dtask_*`). Each continuation creates a distinct Sachima Turn backed by a distinct ARS Run; the same card appends or updates a bounded round row keyed internally by `turn_key`. ARS and Sachima durable state remain authoritative, while Feishu delivery stores only the card message binding and settled projection state.

**Tech stack:** Existing Sachima native delegation coordinator/state store, existing Feishu interactive-card sender and `im.v1.message.patch` path, Python frozen dataclasses, pytest. No new package is planned.

---

## 1. Product decision

A native delegation is a durable Task thread, not necessarily one execution:

```text
Sachima Task (task_ref / dtask_*)
├─ Round 1: Sachima Turn 1 → ARS Run 1
├─ Round 2: Sachima Turn 2 → ARS Run 2
└─ Round N: Sachima Turn N → ARS Run N
```

The product therefore uses:

- **one Feishu card per `task_ref`;**
- **one round row per `turn_key`;**
- one current/latest-round projection at the card header;
- in-place card updates for accepted, running, completed, failed, and cancelled states;
- no new card merely because a continuation creates another Run.

The card is a presentation surface only. It does not create Runs, prove Session reuse, authorize actions, or replace durable task/result records.

## 2. User-visible card contract

### 2.1 Stable Task header

The header remains stable across rounds:

```text
🤝 委派任务
💡 <concise human task description>
🆔 <complete copyable dtask_*>
🤖 <canonical ARS agent_id> · <model> · <optional effort>
🔄 当前状态：<latest round status>
```

Rules:

- Use a concise human goal, never the raw execution/acceptance prompt.
- Show the complete actionable `dtask_*`; do not expose routine `dres_*`, internal `turn_key`, ARS Run ID, ARS Session ID, prompts, credentials, or event logs.
- The executor is the canonical live ARS `agent_id`. For OMP this is `oh-my-pi`, never `omp`.
- Omit effort when unavailable instead of rendering an empty field or dangling separator.
- UTC timestamps come from persisted lifecycle transitions, not render-time `now`.

### 2.2 Round history

Each round displays bounded, independently meaningful status:

```text
执行记录

✅ 第 1 轮：建立 Session 上下文
   受理：08:00 UTC
   完成：08:01 UTC
   Session：新建
   结果：上下文已建立

▶️ 第 2 轮：验证 Session 上下文复用
   受理：08:02 UTC
   Session：复用第 1 轮
   状态：执行中
```

Round rules:

- Number rounds by the durable `turn_keys` order under the Task binding.
- Persist a concise round purpose at Turn creation/continuation time; do not infer it later from opaque result text.
- Preserve settled prior rounds when a continuation starts.
- Show at most the latest three rounds in the card, plus `另有 N 轮`; complete history remains available through the existing task/result query surfaces or a later dedicated details surface.
- A failed or cancelled round does not erase successful prior rounds.

### 2.3 Status semantics

Task header status is a projection of the latest/current round, not an irreversible Task terminal:

```text
latest round completed
→ continuation accepted
→ round N running
→ round N completed | failed | cancelled
```

Required visible states:

- `第 N 轮已受理`
- `第 N 轮执行中`
- `第 N 轮已完成`
- `第 N 轮已失败`
- `第 N 轮已取消`
- `第 N 轮状态待恢复` when submission/delivery truth is uncertain

Do not send another generic “same Task completed” message for every continuation. The round number and purpose make each transition unambiguous.

## 3. Session reuse contract

Equal Task IDs do not prove ARS Session reuse. The card may display `Session：已确认复用` only when trusted backend evidence proves all of the following:

- the two rounds belong to the same Sachima Task;
- the rounds have different ARS Run identities;
- both Runs reference the same ARS Session identity;
- the first relevant round records Session creation;
- the continuation records Session load/reuse;
- both observations are settled and source-bound.

If evidence is incomplete, display `Session：复用状态未确认` or omit the Session line. Never infer reuse from model recall, equal `dtask_*`, similar text, or a successful response.

The card exposes only the safe conclusion. Full Run/Session/event evidence remains in backend state and diagnostics.

### Example: Session reuse test

```text
🤝 委派任务
💡 验证 oh-my-pi 的 Session 复用
🆔 dtask_...
🤖 oh-my-pi · zhipu-coding-plan/glm-5.3 · max
✅ 当前状态：第 2 轮已完成

执行记录
✅ 第 1 轮：建立 Session 上下文
   Session：新建
   结果：上下文已建立
✅ 第 2 轮：验证 Session 上下文复用
   Session：已确认复用
   结果：3 项上下文准确回忆
```

## 4. Durable projection and identity model

Persist card projection state alongside Sachima-owned delegation state, conceptually:

```text
task_ref
├─ feishu_card_message_id
├─ card_sink_state: pending | confirmed | failed | uncertain
├─ last_projected_revision
└─ rounds[]
   ├─ turn_key
   ├─ round_number
   ├─ purpose
   ├─ lifecycle/status timestamps
   ├─ safe result/reason summary reference
   └─ session_projection: new | reused | unconfirmed | omitted
```

Invariants:

- `task_ref → card message_id` is at most one confirmed active card binding per Feishu origin.
- `turn_key → round_number` is stable, append-only, and idempotent.
- A duplicate accepted/terminal event updates the existing round; it cannot append a duplicate round.
- Card rendering uses a monotonically increasing durable projection revision so an older retry cannot overwrite a newer state.
- Origin/chat/thread ownership remains sealed; a restored task cannot patch a card in another origin.
- Store no raw card JSON, raw exception, raw result body, credential, or platform token in delegation state.

The existing task binding and result records remain authoritative. Card state records delivery/projection facts only.

## 5. Delivery behavior

### 5.1 Initial send

On the first accepted round:

1. persist the Task/Turn lifecycle transition;
2. render a sanitized interactive card snapshot;
3. send one Feishu `interactive` message;
4. persist the confirmed `message_id` and projected revision only after delivery ACK;
5. if the send outcome is uncertain, do not blindly create another card during automatic recovery.

### 5.2 In-place updates

For subsequent lifecycle changes and continuation rounds:

1. rebuild the complete bounded snapshot from durable state;
2. patch the same interactive message using `im.v1.message.patch`;
3. coalesce intermediate updates instead of patching every event;
4. force a bounded best-effort final patch for completed/failed/cancelled states;
5. never block ARS execution or final Hermes response on card pacing/retry.

A typical running-state cadence may be 3–5 seconds, but implementation must reuse one named display-layer setting with explicit unit/default/restart semantics rather than embedding scattered timing literals.

### 5.3 Failure and recovery

- Retry only transient Feishu send/patch failures with bounded backoff.
- Keep merging newer revisions while a retry waits.
- A stale retry must not overwrite a newer terminal projection.
- After non-retryable or exhausted final patch failure, send at most one compact sanitized Markdown notice and keep backend state authoritative.
- Never fall back by dumping the full task-workbench/progress panel or raw card payload into chat.
- Startup reconciliation may patch a confirmed existing card from durable state; it must not duplicate a card when the prior send outcome is uncertain.

## 6. Interaction contract

Initial implementation may include one state-changing action:

- **取消当前轮次** — visible only while the latest round is cancellable; it targets the current ARS Run through the existing controlled cancellation path.

Rules:

- The button cancels the current Run, never the durable Task or ARS Session.
- Callback handling rechecks current Task/Turn/Run binding, lifecycle, origin, and idempotency before acting.
- A stale button from an earlier round returns a compact “该轮次已结束” result and performs no cancellation.
- No approve/merge/deploy/permission action is added to this card.
- A read-only “查看状态” action is optional only if it uses an existing safe query surface; it is not required for the first implementation.

## 7. Separation from Task Workbench TODOs

The delegation status card and the existing Task Workbench card remain separate surfaces:

- **Delegation status card:** external AGENT Task/round lifecycle, current Run, bounded result/reason, Session reuse conclusion.
- **Task Workbench:** Hermes transaction plan, TODO hierarchy, controller and leaf ownership, recent sanitized operations.

Executor labels follow actual ownership:

```text
▸ [hermes] 完成委派任务 1/2
  ▶️ [oh-my-pi] 实现并验证冒泡排序
  ⏳ [hermes] 核验 ARS 结果与运行证据
```

The delegated leaf uses `oh-my-pi`; Hermes-owned orchestration, verification, Git/PR, or delivery leaves use `hermes`. TODO state does not prove that an ARS Run exists.

## 8. Implementation stages

### S0 — Preflight and contract reconciliation

**Objective:** Confirm the existing native delegation state, Feishu card APIs, and lifecycle notification sinks before source edits.

**Inspect:**

- `gateway/sachima_delegate.py`
- `gateway/sachima_delegate_state.py`
- `gateway/sachima_delegate_result.py`
- `gateway/sachima_delegate_summary.py`
- `gateway/platforms/feishu.py`
- `gateway/run.py`
- corresponding delegation and Feishu tests

**Exit:** A source-backed mapping identifies Task, Turn, Run, Session, origin, accepted receipt, terminal result, cancellation, existing card send/patch seams, and the exact plain-text paths to replace or retain as fallback.

### S1 — Persist Task-card and round projection state

**Objective:** Add restart-safe, origin-bound, revisioned card projection state without sending a card.

**Likely files:**

- Modify: `gateway/sachima_delegate_state.py`
- Create: `gateway/sachima_delegate_card.py`
- Test: `tests/gateway/test_sachima_delegate_state.py`
- Create test: `tests/gateway/test_sachima_delegate_card.py`

**TDD:** Cover stable round numbering, duplicate-event idempotency, origin binding, revision monotonicity, bounded history, safe canonical `agent_id`, restart roundtrip, and rejection of raw/unsafe material.

**Exit:** A fresh store reconstructs the exact safe card snapshot and cannot duplicate or reorder rounds.

### S2 — Render the native Feishu card

**Objective:** Build a deterministic, sanitized Feishu-native card from the persisted snapshot.

**Likely files:**

- Modify: `gateway/sachima_delegate_card.py`
- Test: `tests/gateway/test_sachima_delegate_card.py`
- Test: `tests/gateway/test_feishu_progress_cards.py` or the closest existing Feishu card test module identified in S0

**TDD:** Cover Chinese/English labels, accepted/running/terminal states, full Task ID, canonical `oh-my-pi`, optional effort omission, three-round overflow, unsafe text redaction, no internal IDs, and native card schema validity.

**Exit:** The renderer emits one bounded native card payload and a separate compact Markdown fallback; neither contains raw prompts/results/events/secrets.

### S3 — Send once and patch across continuations

**Objective:** Replace per-transition lifecycle message spam with one Task-owned card on Feishu while preserving non-Feishu text behavior.

**Likely files:**

- Modify: `gateway/sachima_delegate.py`
- Modify: `gateway/run.py`
- Modify only if required by the proven seam: `gateway/platforms/feishu.py`
- Test: `tests/gateway/test_sachima_delegate_coordinator.py`
- Test: `tests/gateway/test_sachima_delegate_gateway.py`
- Test: relevant Feishu adapter tests

**TDD:** Cover first send, same-message patch, continuation reuse, two Turns under one Task, duplicate terminal reconciliation, restart recovery, transient retry/coalescing, stale-revision rejection, final flush, compact fallback, and non-Feishu plain Markdown compatibility.

**Exit:** One `dtask_*` creates one Feishu card; every continuation patches it and adds exactly one round.

### S4 — Controlled cancellation action

**Objective:** Bind “取消当前轮次” to the latest cancellable Run without changing Task or Session lifecycle semantics.

**Likely files:**

- Modify: `gateway/sachima_delegate_card.py`
- Modify: Feishu callback/control routing identified in S0
- Modify: coordinator callback seam only as required
- Test: callback, coordinator, and Feishu card tests

**TDD:** Cover valid current-round cancellation, stale round, already-terminal round, repeated callback, wrong origin, unknown Task, callback after continuation, and cancellation result patch.

**Exit:** The action is head/current-turn guarded, idempotent, and cannot cancel an earlier Run, Task, or Session.

### S5 — Session-reuse and live-path acceptance

**Objective:** Verify the exact multi-round problem that motivated the design.

**Deterministic acceptance:**

- one Task, two Turns, two distinct ARS Runs, one ARS Session;
- round 1 records Session create;
- round 2 records Session load;
- one Feishu card is sent and subsequently patched;
- both round rows remain visible and independently terminal;
- card displays `Session：已确认复用` only after trusted evidence;
- duplicate reconciliation does not create another card or round;
- card failure does not alter ARS/task truth.

A real Feishu/ARS/`oh-my-pi` canary, Gateway restart, or runtime activation requires separate explicit approval after source implementation and deterministic tests pass.

## 9. Verification

Focused commands are finalized in S0 from the actual test layout. The minimum gate must include:

```bash
uv run pytest -q tests/gateway/test_sachima_delegate_card.py
uv run pytest -q tests/gateway/test_sachima_delegate_state.py
uv run pytest -q tests/gateway/test_sachima_delegate_coordinator.py tests/gateway/test_sachima_delegate_gateway.py
uv run --extra dev --extra messaging --extra feishu pytest -q tests/gateway/test_feishu.py tests/gateway/test_run_progress_topics.py --tb=short
uv run ruff check gateway/sachima_delegate*.py gateway/run.py gateway/platforms/feishu.py tests/gateway
python -m py_compile gateway/sachima_delegate*.py gateway/run.py gateway/platforms/feishu.py

git diff --check
```

Acceptance also requires:

- card JSON redaction and bounded-size tests;
- send/patch/final-flush failure tests;
- persisted final state and visible final card state both verified;
- non-Feishu fallback compatibility;
- independent blocker review focused on identity confusion, duplicate cards/rounds, stale patches, callback scope, and secret leakage.

## 10. Acceptance criteria

Source implementation is complete only when:

- one Sachima Task maps to at most one confirmed active Feishu delegation card per origin;
- each distinct Turn/ARS Run maps to exactly one stable round row;
- continuation patches the existing card instead of creating a new lifecycle message/card;
- prior settled rounds remain visible and immutable when a new round starts;
- header status truthfully identifies the latest round and never treats round 1 completion as permanent Task closure;
- `oh-my-pi` is displayed from canonical ARS `agent_id`; `omp` is never generated;
- Session reuse is shown only from trusted same-Session/different-Run/create-then-load evidence;
- cancellation targets only the current Run and is stale-round/idempotency guarded;
- duplicate/recovered events cannot create duplicate cards, rounds, terminal updates, or cancellations;
- card send/patch failure cannot block or rewrite ARS/task truth;
- rich-card failure falls back at most once with compact sanitized Markdown;
- raw prompts, result bodies, reasoning, events, commands, credentials, internal refs, Run IDs, Session IDs, and card JSON are absent from user-visible output and unsafe logs;
- existing Task Workbench TODO semantics and non-Feishu delegation behavior remain green.

## 11. Non-goals and authorization boundaries

Saving or accepting this plan authorizes only this documentation artifact. It does not authorize:

- source or test implementation;
- commit/push/PR/merge/release/deployment beyond committing this plan document under the existing repository convention;
- Gateway/service restart or runtime configuration change;
- a real Feishu/ARS/AGENT canary;
- ARS core, API, Session, Run, Profile, Binding, storage, roster, model, effort, or permission changes;
- merging the delegation status card into the existing Task Workbench card;
- exposing full results, internal IDs, prompts, reasoning, tool logs, or event streams;
- cancelling a whole Task or Session;
- approval, merge, deployment, or permission buttons.

## 12. Rollback

The feature must remain reversible at the presentation boundary:

1. stop sending/patching delegation status cards;
2. restore the existing compact plain Markdown lifecycle notifications;
3. retain Task, Turn, ARS Run/Session, result, and summary state unchanged;
4. leave historical card bindings inert for audit/reconciliation rather than deleting platform messages automatically;
5. perform no ARS migration or Session reset.

Runtime rollback, deployment, and Gateway restart remain separately authorized operations.
