# Sachima Native Delegation Status Card — Implementation Plan

> **Type:** Implementation plan (candidate)
> **Status:** Product design accepted; source implementation is not authorized
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

### 2.1 Card summary and field order

The card uses the fixed title form `card type · latest round state`, followed by one compact, fixed-order summary block. A completed second round renders as:

```text
委派任务 · 第 2 轮已完成

💡 任务： <一句话任务目标概要>
🆔 编号： <完整可复制的 dtask_*>
⏱️ 耗时： <任务累计耗时>
🤖 执行： <canonical ARS agent_id> · <model> · <optional effort>
👤 角色： <AGENT role or honest unavailable value>
```

The same five fields and their order remain stable in created, waiting, submitting, accepted, running, failed, cancelled, and recovery states. There are no list bullets, hierarchy dots, or blank lines between field rows; each row begins directly with its Emoji. The title identifies the latest round state without presenting the Task as irreversibly closed.

Rules:

- Use a concise one-sentence human goal, never the raw execution/acceptance prompt. The visible label is `任务`.
- Show the complete actionable `dtask_*`; do not expose routine `dres_*`, internal `turn_key`, ARS Run ID, ARS Session ID, prompts, credentials, or event logs.
- The visible label is `编号`, and the value is copyable plain text rather than a shortened or masked identifier.
- `耗时` is the Task lifecycle duration, never the current timestamp or card send time. Its start boundary is the persisted `task_created_at` written when Sachima durably allocates the Task/origin binding. While the latest round is active, the end boundary is the persisted projection-update instant selected for that snapshot; at a settled latest-round terminal, the end boundary is that terminal's persisted settlement time. A continuation resumes the same Task's duration projection and a terminal value remains fixed until another continuation starts. The renderer uses only persisted lifecycle evidence and must render an honest unavailable value when either boundary is missing; it must not invent a duration.
- `执行` is `<canonical ARS agent_id> · <model> · <optional effort>`. For OMP the agent ID is `oh-my-pi`, never `omp`.
- `角色` is the AGENT role sealed into the admitted Task/Turn execution contract. It must come from the validated role/preset selection used for that execution, not from model output, display-name guessing, a platform identity, or card copy. If the AGENT was selected directly and no role was assigned, render `未指定` in Chinese or `Not specified` in English instead of inventing a role.
- Omit effort when unavailable instead of rendering an empty field or dangling separator.
- A Chinese card uses `任务 / 编号 / 耗时 / 执行 / 角色`, a full-width colon, and exactly one following space. An English card uses `Task / ID / Duration / Execution / Role`, an ASCII colon, and exactly one following space. One card is localized consistently; labels must not mix languages.
- Feishu native rendering may apply bold label weight, but the compact Markdown fallback must preserve the same wording, order, punctuation, duration semantics, and no-bullet layout.
- The confirmed native header templates are blue for `已创建`, yellow for `执行中`, and green for `已完成`. S0 must map the remaining accepted/waiting/submitting/failed/cancelled/recovery states to existing Feishu templates without changing the confirmed three; unverified color choices are implementation details, not new product states.
- Production cards do not contain the visual-review footer `状态预览 N/4 · 非实时卡片`; that footer belongs only to the four separately sent review cards.
- `执行` uses a deterministic user-facing label derived from the admitted execution contract. The confirmed OMP visual is `oh-my-pi · glm-5.3 · max`; any provider-prefix shortening must be unambiguous, source-backed, and covered by renderer tests rather than inferred from result text.

### 2.2 Round history

Each round displays bounded, independently meaningful status without repeating the five-field summary or exposing internal timestamps/identities:

```text
执行记录

✅ 第 1 轮：建立 Session 上下文
Session：新建
结果：上下文已建立

▶️ 第 2 轮：验证 Session 上下文复用
Session：复用状态确认中
状态：执行中
```

Round rules:

- Number rounds by the durable `turn_keys` order under the Task binding.
- Persist a concise round purpose at Turn creation/continuation time; do not infer it later from opaque result text.
- Preserve settled prior rounds when a continuation starts.
- Show at most the latest three rounds in the card, plus `另有 N 轮`; complete history remains available through the existing task/result query surfaces or a later dedicated details surface. This is the first-slice product display contract: unit = round rows per card, default = 3, maximum = 3, scope = Feishu card rendering only, and it is neither a retention nor a safety limit. Changing it requires a reviewed config/code change and Gateway restart; S0 must replace it only if verified Feishu payload constraints require a lower maximum.
- A failed or cancelled round does not erase successful prior rounds.

### 2.3 Status semantics

Task header status is a projection of the latest/current round, not an irreversible Task terminal:

```text
latest round completed
→ continuation accepted
→ round N running
→ round N completed | failed | cancelled
```

Required visible title states use the same `委派任务 · <state>` structure:

- `委派任务 · 已创建`
- `委派任务 · 等待执行槽位`
- `委派任务 · 第 1 轮提交中`
- `委派任务 · 第 1 轮未受理` when submission fails before ARS acceptance
- `委派任务 · 第 N 轮已受理`
- `委派任务 · 第 N 轮执行中`
- `委派任务 · 第 N 轮已完成`
- `委派任务 · 第 N 轮已失败`
- `委派任务 · 第 N 轮已取消`
- `委派任务 · 第 N 轮状态待恢复` when submission/delivery truth is uncertain

English cards use the same type/state structure in Title Case, for example `Delegated Task · Created`, `Delegated Task · Round 2 Running`, and `Delegated Task · Round 2 Completed`.

Do not send another generic “same Task completed” message for every continuation. The round number and purpose make each transition unambiguous. Intermediate states may be coalesced for delivery pacing; the product contract does not require every transient state to visibly flash once, but every delivered snapshot must be truthful and monotonic.

### 2.4 Confirmed Session-reuse visual snapshots

The user-confirmed Feishu effect is represented by these four snapshots. They are four review snapshots of one logical card, not four production messages; production patches the same `message_id` in place.

**Snapshot 1 — created**

```text
委派任务 · 已创建

💡 任务： 验证 oh-my-pi 的 Session 复用
🆔 编号： dtask_<完整可复制编号>
⏱️ 耗时： 0秒
🤖 执行： oh-my-pi · glm-5.3 · max
👤 角色： 未指定

执行记录
⏳ 尚未开始
```

**Snapshot 2 — round 1 running**

```text
委派任务 · 第 1 轮执行中

💡 任务： 验证 oh-my-pi 的 Session 复用
🆔 编号： dtask_<完整可复制编号>
⏱️ 耗时： <真实累计耗时>
🤖 执行： oh-my-pi · glm-5.3 · max
👤 角色： 未指定

执行记录
▶️ 第 1 轮：建立 Session 上下文
Session：新建
状态：执行中
```

**Snapshot 3 — round 2 running**

```text
委派任务 · 第 2 轮执行中

💡 任务： 验证 oh-my-pi 的 Session 复用
🆔 编号： dtask_<完整可复制编号>
⏱️ 耗时： <真实累计耗时>
🤖 执行： oh-my-pi · glm-5.3 · max
👤 角色： 未指定

执行记录
✅ 第 1 轮：建立 Session 上下文
Session：新建
结果：上下文已建立

▶️ 第 2 轮：验证 Session 上下文复用
Session：复用状态确认中
状态：执行中
```

**Snapshot 4 — round 2 completed**

```text
委派任务 · 第 2 轮已完成

💡 任务： 验证 oh-my-pi 的 Session 复用
🆔 编号： dtask_<完整可复制编号>
⏱️ 耗时： <真实最终耗时>
🤖 执行： oh-my-pi · glm-5.3 · max
👤 角色： 未指定

执行记录
✅ 第 1 轮：建立 Session 上下文
Session：新建
结果：上下文已建立

✅ 第 2 轮：验证 Session 上下文复用
Session：已确认复用
结果：上下文验证通过
```

The preview durations used during visual review were illustrative. Production must derive every duration from persisted Task lifecycle boundaries; it must not copy preview numbers into runtime output.

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
委派任务 · 第 2 轮已完成

💡 任务： 验证 oh-my-pi 的 Session 复用
🆔 编号： dtask_...
⏱️ 耗时： <真实最终耗时>
🤖 执行： oh-my-pi · zhipu-coding-plan/glm-5.3 · max
👤 角色： session_reuse_verifier

执行记录
✅ 第 1 轮：建立 Session 上下文
Session：新建
结果：上下文已建立

✅ 第 2 轮：验证 Session 上下文复用
Session：已确认复用
结果：3 项上下文准确回忆
```

If this task was admitted by direct AGENT selection rather than the `session_reuse_verifier` role, the same card renders `👤 角色： 未指定`; it never substitutes a descriptive display label for absent admission evidence.

## 4. Durable projection and identity model

Persist card projection state alongside Sachima-owned delegation state, conceptually:

```text
task_ref
├─ task_created_at
├─ feishu_card_message_id
├─ card_sink_state: pending | confirmed | failed | uncertain
├─ last_projected_revision
├─ last_projected_at
├─ pre_accept_status: created | waiting | submitting | rejected | omitted
└─ rounds[]
   ├─ turn_key
   ├─ round_number
   ├─ purpose
   ├─ admitted_role
   ├─ lifecycle/status timestamps
   ├─ safe result/reason summary reference
   └─ session_projection: new | reused | unconfirmed | omitted
```

Invariants:

- `task_created_at` is written exactly once with the durable Task/origin allocation and is the duration start boundary; `last_projected_at` and settled round terminal timestamps are persisted projection evidence, not render-time clocks.
- `task_ref → card message_id` is at most one confirmed active card binding per Feishu origin.
- `turn_key → round_number` is stable, append-only, and idempotent.
- A duplicate accepted/terminal event updates the existing round; it cannot append a duplicate round.
- Card rendering uses a monotonically increasing durable projection revision so an older retry cannot overwrite a newer state.
- Origin/chat/thread ownership remains sealed; a restored task cannot patch a card in another origin.
- Allocating a user-visible `task_ref` creates durable Task-card projection state before queue waiting or ARS submission. A pre-accept failure may remove execution-only Turn state only after a terminal card projection/tombstone is durable; it must not erase the user-visible Task/card identity.
- Store no raw card JSON, raw exception, raw result body, credential, or platform token in delegation state.

The existing task binding and result records remain authoritative. Card state records delivery/projection facts only.

## 5. Delivery behavior

### 5.1 Initial send and pre-accept identity

The complete `dtask_*` becomes user-visible only through the first card snapshot or its explicit degraded fallback. Card creation therefore occurs when the Task/origin binding is durably allocated, before capacity waiting and before ARS submission:

1. persist the Task/origin binding, immutable `task_created_at`, and initial `委派任务 · 已创建` projection;
2. render a sanitized interactive card snapshot containing the complete copyable `dtask_*`;
3. send one Feishu `interactive` message;
4. persist the confirmed `message_id`, projected revision, and `last_projected_at` only after delivery ACK;
5. patch the same card through `委派任务 · 等待执行槽位`, `委派任务 · 第 1 轮提交中`, and the accepted/running/terminal states;
6. if pre-accept submission fails, preserve a terminal `第 1 轮未受理` projection and the Task/card binding even if execution-only Turn state is cleaned up;
7. if the initial send outcome is uncertain, do not blindly create another card during automatic recovery; emit at most one explicit degraded Markdown fallback and retain the uncertain binding for operator reconciliation.

Normal-path invariant: no ordinary lifecycle text may expose a new `dtask_*` before the Task-card projection exists. Feishu delivery failure is an explicit degraded presentation state, not permission to fabricate a confirmed card.

### 5.2 In-place updates

For subsequent lifecycle changes and continuation rounds:

1. rebuild the complete bounded snapshot from durable state;
2. patch the same interactive message using `im.v1.message.patch`;
3. coalesce intermediate updates instead of patching every event;
4. select one final projection revision and make one projection-layer adapter call for completed/failed/cancelled states; the adapter retains its existing transport retry policy;
5. never block ARS execution or final Hermes response on card pacing/retry.

S0 must define one config-backed `running_patch_interval_seconds` contract from verified Feishu rate/payload constraints and the existing adapter behavior: provenance, unit, default, allowed maximum, invalid-value handling, scope, and restart semantics must be written into the implementation/tests before S1 starts. This plan deliberately sets no speculative cadence.

### 5.3 Failure and recovery

- The existing Feishu adapter owns transport-level transient retry/backoff. The projection layer must not wrap it in a second retry loop; it performs at most one adapter call per selected projection revision and relies on later lifecycle reconciliation or startup recovery for another attempt.
- Keep merging newer revisions while an adapter call or later reconciliation is pending.
- A stale retry must not overwrite a newer terminal projection.
- After non-retryable or exhausted final patch failure, send at most one compact sanitized Markdown notice and keep backend state authoritative.
- Never fall back by dumping the full task-workbench/progress panel or raw card payload into chat.
- Startup reconciliation may patch a confirmed existing card from durable state; it must not duplicate a card when the prior send outcome is uncertain.

### 5.4 Numeric and retry contract

| Resource | Contract for this plan | Provenance and restart semantics |
|---|---|---|
| Visible round rows | Unit: round rows per Feishu card; default = 3; maximum = 3 for the first slice. | Product readability/bounded-card decision, not retention or safety. A change needs reviewed config/code plus Gateway restart; S0 may only lower it when verified Feishu constraints require that. |
| Running patch cadence | `running_patch_interval_seconds`; unit = seconds. No value is approved yet. | S0 must derive and record default, allowed maximum, invalid-value behavior, and restart semantics from current Feishu constraints and adapter behavior before S1. Missing this contract blocks implementation. |
| Card payload size | Unit and maximum follow the verified Feishu interactive-card API/SDK constraint observed in S0; no guessed repository constant is approved here. | S0 records the authoritative source and deterministic renderer failure behavior. The renderer must fail closed or compact before the adapter call; it must not rely on API rejection as normal control flow. |
| Projection retry attempts | Exactly one projection-layer adapter call per selected revision. | The existing Feishu adapter exclusively owns transport retry/backoff. Do not multiply its attempt count in the projection layer. Adapter-policy changes retain their own existing config/code and restart contract. |
| Degraded Markdown notices | At most one notice per Task/card sink failure episode. | Idempotency cardinality, not a rate or safety threshold; it is persisted with sink settlement and is not configurable. |

### 5.5 First activation and existing Tasks

- Do not automatically backfill historical settled Tasks that predate card projection.
- An existing Task without a card that receives a new continuation creates its Task card before that continuation becomes user-visible, reconstructing only safe persisted round summaries.
- Existing active legacy Tasks without card bindings stay on the legacy lifecycle path until their next durable transition; startup must not guess a card binding or duplicate earlier messages.
- Existing confirmed card bindings are reconciled normally after restart. Old receipt message IDs are not silently promoted into card bindings.

## 6. Interaction contract

The core first implementation is read-only presentation. A later separately approved optional slice may include one state-changing action:

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

**Exit:** A source-backed mapping identifies Task, Turn, Run, Session, origin, pre-accept Task-ID exposure, accepted receipt, terminal result, cancellation, existing card send/patch seams, and the exact plain-text paths to replace or retain as fallback. S0 also closes every numeric contract above, including its authoritative source, unit, default versus maximum, validation behavior, scope, and restart semantics; S1 cannot start while any such value is unresolved.

### S1 — Persist Task-card and round projection state

**Objective:** Add restart-safe, origin-bound, revisioned card projection state without sending a card.

**Likely files:**

- Modify: `gateway/sachima_delegate_state.py`
- Create: `gateway/sachima_delegate_card.py`
- Test: `tests/gateway/test_sachima_delegate_state.py`
- Create test: `tests/gateway/test_sachima_delegate_card.py`

**TDD:** Cover immutable `task_created_at`, persisted projection/terminal duration boundaries, stable round numbering, duplicate-event idempotency, origin binding, revision monotonicity, bounded history, safe canonical `agent_id`, admitted-role persistence, restart roundtrip, and rejection of raw/unsafe material.

**Exit:** A fresh store reconstructs the exact safe card snapshot and cannot duplicate or reorder rounds.

### S2 — Render the native Feishu card

**Objective:** Build a deterministic, sanitized Feishu-native card from the persisted snapshot.

**Likely files:**

- Modify: `gateway/sachima_delegate_card.py`
- Test: `tests/gateway/test_sachima_delegate_card.py`
- Test: `tests/gateway/test_feishu_progress_cards.py` or the closest existing Feishu card test module identified in S0

**TDD:** Cover Chinese/English whole-card localization, `card type · latest round state` titles, the fixed `任务/编号/耗时/执行/角色` and `Task/ID/Duration/Execution/Role` orders, full-width versus ASCII colon rules, no-bullet/no-blank-row layout, persisted Task-duration calculation for running and terminal snapshots, continuation duration resumption, missing-boundary fallback, full Task ID, canonical `oh-my-pi`, admitted-role rendering and exact `未指定` / `Not specified` fallback, optional effort omission, the four confirmed Session-reuse snapshots, three-round overflow, unsafe text redaction, no internal IDs, compact-Markdown parity, and native card schema validity.

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

### S4 — Optional controlled cancellation action (separate approval)

**Objective:** Only after separate source and live-control approval, bind “取消当前轮次” to the latest cancellable Run without changing Task or Session lifecycle semantics. S4 is not required for the read-only status-card acceptance in S5.

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
- one Feishu card is sent before the Task ID is exposed through ordinary lifecycle output and is subsequently patched through the four confirmed visual snapshots (`已创建`, round 1 running, round 2 running, round 2 completed);
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

- card JSON redaction and payload-size tests against the S0-recorded Feishu maximum;
- pre-accept waiting/submitting/rejected tests and first-activation legacy-Task tests;
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
- the summary preserves the fixed localized `任务/编号/耗时/执行/角色` or `Task/ID/Duration/Execution/Role` field order, punctuation, and no-bullet layout; derives duration only from persisted Task lifecycle boundaries; and shows only the role sealed into the admitted execution contract, with the exact honest fallback when none was assigned;
- Session reuse is shown only from trusted same-Session/different-Run/create-then-load evidence;
- if separately approved and implemented, cancellation targets only the current Run and is stale-round/idempotency guarded;
- duplicate/recovered events cannot create duplicate cards, rounds, terminal updates, or cancellations;
- card send/patch failure cannot block or rewrite ARS/task truth;
- rich-card failure falls back at most once with compact sanitized Markdown;
- raw prompts, result bodies, reasoning, events, commands, credentials, non-user-facing internal refs (`dres_*`, `turn_key`, Run IDs, Session IDs), and card JSON are absent from user-visible output and unsafe logs; the complete `dtask_*` is the deliberate user-facing exception;
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
- any cancellation button or live cancellation action without the separate S4 approval, and cancelling a whole Task or Session under any status-card approval;
- approval, merge, deployment, or permission buttons.

## 12. Rollback

The feature must remain reversible at the presentation boundary:

1. stop sending/patching delegation status cards;
2. restore the existing compact plain Markdown lifecycle notifications;
3. retain Task, Turn, ARS Run/Session, result, and summary state unchanged;
4. leave historical card bindings inert for audit/reconciliation rather than deleting platform messages automatically;
5. perform no ARS migration or Session reset.

Runtime rollback, deployment, and Gateway restart remain separately authorized operations.
