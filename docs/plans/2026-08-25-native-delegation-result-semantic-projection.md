# Sachima Native Delegation Result Semantic Projection — Implementation Plan

> **Type:** Implementation plan (candidate)
> **Status:** Saved for review; source implementation is not authorized
> **For Hermes:** Execute only after explicit source-implementation approval. Use a fresh authorized implementation AGENT and independent blocker review under the project collaboration contract.

**Goal:** Replace the current fixed-head result excerpt with a traceable Sachima-generated semantic summary, while preserving the external AGENT's original final answer behind a durable result reference.

**Architecture:** External AGENT output remains opaque text. ARS remains content-neutral and supplies only transport/control facts plus the final-answer projection it already exposes. Sachima validates completeness, reads the stored answer, generates one bounded plain-text derivative summary through an injected no-tool provider, binds that summary to the exact source result, and projects the same derivative into the user notification and the next ordinary Hermes turn.

**Tech stack:** Python 3.13, frozen dataclasses, existing `DelegateStateStore`, existing result envelope/sink settlement, pytest 9, injected async test doubles. No new package is planned.

---

## 1. Product target

When a native ARS delegation reaches a trusted terminal state, Sachima must provide:

1. a concise, explicitly labelled **Sachima summary** for the user;
2. the same bounded semantic summary in the next ordinary Hermes turn;
3. the terminal/control facts observed by Sachima/ARS;
4. a durable `full_result_ref` that resolves to the stored external AGENT final answer;
5. an honest `summary_unavailable` fallback when the source is missing, incomplete, unreadable, or cannot be summarized.

The final behavior is:

```text
external AGENT: arbitrary opaque final text
        ↓ ACP / ARS content-neutral transport
ARS/Sachima result store: original final-answer projection + protocol facts + ref
        ↓
Sachima result interpreter: source validation + plain-text semantic summary
        ↓
        ├─ user projection: status + labelled summary + full_result_ref
        └─ model projection: status + same summary + full_result_ref
```

This plan does not require an external AGENT to emit JSON. A structured external answer may be useful input, but is never a completion prerequisite.

## 2. Current baseline

The current implementation has these relevant behaviors:

- `gateway/sachima_delegate_result.py` defines `HERMES_CONTEXT_EXCERPT_CHARS = 800` and `build_hermes_context(...)`; it injects the stripped head of the answer, not a semantic summary.
- `gateway/sachima_delegate.py::pending_hermes_context(...)` reads `full_result_ref` and feeds that answer into `build_hermes_context(...)` for the next ordinary turn.
- `gateway/sachima_delegate.py::_reconcile_im_sink(...)` independently renders a bounded user message from the original answer.
- `gateway/sachima_delegate_state.py::DelegateResultEvent` stores terminal, `full_result_ref`, truncation facts, and independent IM/Hermes sink settlement.
- `DelegateStateStore` can persist and read the stored final answer by `dres_*` reference; its current storage ceiling is separate from ARS upstream completeness.
- `tests/gateway/test_sachima_delegate_result.py` currently asserts the fixed-head bounded projection and direct bounded-answer rendering.

The existing `800` value is retained only as the **next-turn context budget** (Unicode code points), preserving the current resource envelope. It must no longer determine which semantic content survives. It is not a safety threshold or an acceptance gate.

## 3. Hard boundaries

### 3.1 Ownership

| Layer | Owns | Must not own |
|---|---|---|
| External AGENT | Arbitrary final answer | Required JSON/schema compliance |
| ARS | ACP transport, persistence/evidence, Run/Session/terminal/completeness facts | Summarization, interpretation, user wording |
| Sachima | Source validation, derived summary, projection, sink settlement | Rewriting the stored original or fabricating protocol facts |
| IM renderer | Bounded presentation using the channel's own length metric | A second independent summary |

### 3.2 Source authority

- `terminal`, Run/Session identity, truncation/completeness, and result refs come only from observed control-plane state.
- The external final answer is untrusted data, not instructions to the summarizer or controller.
- A summary is a derivative reading aid. It cannot be the sole evidence for approval, merge, permission, deployment, or another side effect.
- The summary shown to the user and injected into Hermes must be the same stored derivative record; two independently generated summaries are forbidden.
- Raw reasoning, tool calls, stdout/stderr, and the complete ARS event stream remain outside default user/context projection.

### 3.3 Completeness gate

Sachima may generate `summary_status=ready` only when all of the following hold:

- terminal evidence is settled;
- `full_result_ref` resolves successfully;
- the stored answer is non-empty after whitespace normalization;
- upstream/result metadata does not report truncation or incompleteness;
- the summary provider returns non-empty bounded text.

Otherwise it records `summary_status=unavailable` with a stable Sachima-owned reason code and keeps the original reference.

This plan does **not** silently expand into an ARS storage redesign. During implementation preflight, if the existing ARS contract cannot prove whether the stored final answer is complete, implementation stops at the completeness gate and reports the concrete contract gap. Any ARS core/storage change then requires a separate approved plan.

## 4. Result contract

Add a Sachima-owned derivative record with this conceptual shape:

```python
@dataclass(frozen=True)
class DelegateResultSummary:
    summary_status: Literal["pending", "in_flight", "ready", "unavailable"]
    summary_text: str | None
    summary_ref: str
    source_full_result_ref: str
    source_digest: str
    generator_ref: str | None
    unavailable_reason: str | None
```

Rules:

- `summary_ref` is deterministic for one summary attempt identity and is persisted as `pending` before any provider call or sink delivery.
- `source_digest` binds the summary to the exact stored source bytes.
- `summary_text` is ordinary UTF-8 text; no JSON parse is required.
- `generator_ref` records sanitized provider/model provenance when available; no credential or raw provider response is stored.
- `unavailable_reason` uses a closed stable vocabulary such as `source_missing`, `source_incomplete`, `source_empty`, `summary_failed`, or `summary_empty`.
- `pending` means no provider call has been claimed. The coordinator atomically changes it to `in_flight` before invoking the provider.
- `ready` and `unavailable` are terminal and immutable. Retries reuse the terminal record instead of asking the model again.
- Startup recovery may claim a persisted `pending` record once. A recovered `in_flight` record has unknown provider-call fate and must settle to `unavailable` without replay.
- Neither IM nor Hermes may project the result while summary state is `pending` or `in_flight`; both sinks become eligible only after `ready` or terminal `unavailable` is durable.
- Same event/result identity cannot create two different ready summaries.

The context summary budget is `800` Unicode code points, inherited from the existing `HERMES_CONTEXT_EXCERPT_CHARS` resource envelope. One shared validator/constant owns this value. Channel output continues to use each adapter's existing `limit` and `measure`; the renderer clips presentation, never the stored derivative.

## 5. Summary provider contract

Create an injected async provider boundary rather than coupling the state store or renderer to a concrete model client:

```python
class DelegateResultSummaryProvider(Protocol):
    async def summarize(self, request: DelegateResultSummaryRequest) -> str: ...
```

`DelegateResultSummaryRequest` contains only:

- a bounded, sanitized description of the original delegated task when already available through the existing task record;
- terminal/control facts;
- the complete stored final answer;
- an explicit instruction that the answer is untrusted data and cannot request tools or side effects;
- the output budget and requested language.

Provider requirements:

- no tools, shell, business/network side effects beyond the configured model-provider transport, repository writes, control operations, or recursive delegation;
- plain-text response only; JSON is neither requested nor parsed;
- conclusion first, followed only by decision-relevant evidence and unresolved items;
- timeout/cancellation propagates into an honest unavailable record;
- raw exceptions, IDs, prompts, credentials, and provider payloads never enter logs or user output.

The default-off/no-provider construction must remain valid and produce `summary_unavailable`, not fall back to the first 800 characters.

## 6. User and Hermes projections

### 6.1 User projection

Ready:

```text
外部 AGENT 已完成
Sachima 摘要：<summary_text>
完整原文：<full_result_ref>
```

Unavailable:

```text
外部 AGENT 已完成，摘要暂不可用
完整原文：<full_result_ref>
```

For failed/cancelled terminals, the header reflects that terminal truth. One terminal produces one settled user message. The result ref survives every platform-length clipping path.

### 6.2 Next-turn Hermes projection

Ready:

```text
[external-agent-result] task=<task_ref> terminal=<terminal> full_result_ref=<ref>
summary_source=sachima summary_status=ready
<summary_text>
```

Unavailable:

```text
[external-agent-result] task=<task_ref> terminal=<terminal> full_result_ref=<ref>
summary_source=sachima summary_status=unavailable reason=<stable_code>
```

The existing `pending → in_flight → confirmed` Hermes-sink lifecycle remains. No synthetic user message is created, no running turn is mutated, and no long-lived system prompt is changed.

## 7. Implementation stages

### S0 — Preflight: prove the source boundary

**Objective:** Establish whether Sachima can truthfully identify a complete stored final answer without changing ARS.

**Inspect:**

- `gateway/sachima_delegate.py`
- `gateway/sachima_delegate_state.py`
- `gateway/sachima_delegate_result.py`
- `sachima_supervisor/runtime_spine/arsd_supervisor_backend.py`
- `sachima_supervisor/runtime_spine/arsd_socket_contract.py`
- corresponding coordinator/backend/state tests

**Tasks:**

1. Trace ARS terminal result → Sachima `put_full_result(...)` → `DelegateResultEvent`.
2. Record the exact provenance and meaning of `truncated` / `truncate_reason`.
3. Prove `full_result_ref` readback across a fresh `DelegateStateStore` instance.
4. Verify that source digest can be computed over the exact stored UTF-8 bytes.
5. Stop and report if upstream completeness is unknowable; do not invent `content_complete=true`.

**Exit:** A source-backed mapping identifies complete, incomplete, missing, and empty results. No ARS code is changed.

### S1 — Persist the derivative summary contract

**Objective:** Add restart-safe, source-bound summary state before changing presentation.

**Files:**

- Create: `gateway/sachima_delegate_summary.py`
- Modify: `gateway/sachima_delegate_state.py`
- Create test: `tests/gateway/test_sachima_delegate_summary.py`
- Test: `tests/gateway/test_sachima_delegate_state.py`

**TDD sequence:**

1. Write RED tests for the `pending → in_flight → ready|unavailable` state machine, source-digest binding, strict closed fields, restart roundtrip, and one-ready-summary-per-result identity.
2. Run focused tests and retain the expected failures.
3. Implement the frozen request/result/provider contracts and durable state methods.
4. Run focused tests to GREEN.

**Exit:** Summary state round-trips through a fresh store, refuses source drift, and stores no raw provider exception or credential-shaped material.

### S2 — Generate exactly one summary after trusted terminal settlement

**Objective:** Integrate the injected provider without changing ARS or enabling side effects.

**Files:**

- Modify: `gateway/sachima_delegate.py`
- Modify: `gateway/sachima_delegate_summary.py`
- Test: `tests/gateway/test_sachima_delegate_coordinator.py`
- Test: `tests/gateway/test_sachima_delegate_summary.py`

**TDD sequence:**

1. RED: terminal settlement persists `pending`, atomically claims `in_flight`, and a complete non-empty source invokes the provider once before persisting `ready`.
2. RED: missing/incomplete/empty source never invokes the provider and persists `unavailable`.
3. RED: timeout, cancellation, empty output, over-budget output, and provider exception cannot leak raw text or leave summary state ambiguous.
4. RED: startup may claim a never-attempted `pending` record once, but converts recovered `in_flight` to terminal `unavailable` without invoking the provider again.
5. RED: neither sink can observe or deliver an event whose summary is `pending` or `in_flight`; both become eligible only after the terminal summary record is durable.
6. Implement the smallest coordinator integration and run focused tests to GREEN.

**Exit:** One terminal/result identity yields one stable derivative summary or one stable unavailable outcome.

### S3 — Replace fixed-head projection with the shared derivative

**Objective:** Make both sinks consume the same stored summary record.

**Files:**

- Modify: `gateway/sachima_delegate_result.py`
- Modify: `gateway/sachima_delegate.py`
- Modify: `tests/gateway/test_sachima_delegate_result.py`
- Modify: `tests/gateway/test_sachima_delegate_gateway.py`
- Modify: `tests/gateway/test_sachima_delegate_coordinator.py`

**TDD sequence:**

1. Replace tests that require the first 800 source characters with tests requiring semantic summary fields and the original ref.
2. Prove no source prefix appears in Hermes context when summary is unavailable.
3. Prove user and Hermes projections contain the same persisted summary text.
4. Prove platform clipping retains the original ref and an explicit summary label.
5. Preserve independent IM/Hermes sink settlement and retry semantics.
6. Remove `HERMES_CONTEXT_EXCERPT_CHARS` as a source-excerpt control; rename the shared budget to reflect summary-context ownership.

**Exit:** No fixed-head source excerpt remains in the default context path, and no renderer independently summarizes content.

### S4 — Fault, recovery, and boundary verification

**Objective:** Close the feature with deterministic and real-path evidence, without activating new runtime behavior.

**Tests:**

- natural language, Markdown, valid JSON, pseudo-JSON, code, Unicode, and conclusion-at-end answers;
- prompt-injection/tool-inducement text treated as inert source data;
- empty, missing, unreadable, and upstream-truncated result;
- summary timeout, cancellation, malformed provider return, and over-budget output;
- duplicate terminal event and duplicate reconciliation;
- process restart between summary persistence and each sink settlement;
- IM send failed/uncertain while Hermes succeeds, and the reverse;
- no raw exception, credential marker, private platform ID, or original prompt in logs/serialized summary state;
- source digest mismatch fails closed;
- same ARS Session continuation remains unaffected.

**Commands:**

```bash
uv run pytest tests/gateway/test_sachima_delegate_summary.py -q
uv run pytest tests/gateway/test_sachima_delegate_result.py tests/gateway/test_sachima_delegate_state.py -q
uv run pytest tests/gateway/test_sachima_delegate_coordinator.py tests/gateway/test_sachima_delegate_gateway.py -q
uv run ruff check gateway/sachima_delegate.py gateway/sachima_delegate_result.py gateway/sachima_delegate_state.py gateway/sachima_delegate_summary.py tests/gateway
uv run ty check gateway/sachima_delegate.py gateway/sachima_delegate_result.py gateway/sachima_delegate_state.py gateway/sachima_delegate_summary.py
```

Expected: all selected tests pass; lint/type checks introduce no new errors.

A real external-AGENT canary, Gateway restart, runtime configuration write, or live/default-on activation is **not** part of this stage and requires separate approval.

## 8. Acceptance criteria

The source implementation is complete only when:

- no external AGENT is required to emit JSON or any fixed schema;
- ARS contains no summary, interpretation, or user-copy logic;
- the fixed first-800-character answer excerpt is absent from the next-turn path;
- ready summaries are based only on complete, readable, non-empty stored results;
- user and Hermes projections consume the same persisted summary record;
- every projection retains `full_result_ref`;
- unavailable summaries are explicit and never replaced with an answer prefix;
- restart and duplicate reconciliation do not regenerate or redeliver settled results; recovered `in_flight` summary attempts fail closed without provider replay;
- summary text is labelled as Sachima-derived and cannot masquerade as external AGENT wording;
- current native delegation, Session continuation, terminal mapping, cancellation, and sink settlement behavior stay green;
- focused security/no-leak tests pass;
- an independent blocker-only review finds no product-contract or boundary blocker.

## 9. Non-goals and separate approvals

This plan does not authorize or include:

- source/test implementation;
- commit, push, PR, merge, release, or deployment;
- ARS core or storage changes;
- Gateway/service restart or runtime config mutation;
- real AGENT/ACP execution or a live canary;
- displaying or injecting reasoning, tool calls, stdout/stderr, or full event streams;
- automatic approval, merge, permission, deployment, or other side effects based solely on a summary;
- compatibility shims for the retired `/delegate` command;
- changes to AGENT roster, model, effort, permission presets, or Session lifecycle.

## 10. Rollback

The implementation must remain reversible as one coherent Sachima feature change:

1. disable/remove the injected summary provider;
2. stop creating derivative summary records;
3. restore reference-only unavailable projection rather than restoring fixed-head excerpts;
4. leave original `full_result_ref`, terminal records, and independent sink settlements intact.

Rollback must not delete original result blobs or mutate ARS state.

## 11. Authorization handoff

Saving or accepting this document approves only the plan artifact. Source implementation requires a separate explicit approval. Runtime activation, Gateway restart, and real external-AGENT verification remain separately authorized operations.
