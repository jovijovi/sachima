# Claude Code PRD Final Blocker-Only Re-Review — Task Workbench TODO Lifecycle

> Role: documentation engineer / PRD quality + design-readiness reviewer.
> Mode: final blocker-only re-review after Hermes patched the Codex blockers (governance reconciliation, same-owner-scope isolation, agent TODO hydration safety) and Codex returned `VERDICT: PASS` / 94.
> Scope: PRD/design-readiness review only. No PRD, dev log, Codex review, source, tests, config, Gateway, platform adapters, or roadmap status were modified. No commits, pushes, GitHub actions, restarts, or external side effects. No secrets encountered.
> Reasoning effort: xhigh.

## Reviewed paths

PRD / governance artifacts:

- **PRD under review:** `docs/plans/2026-06-24-task-workbench-todo-lifecycle-prd.md`
- **Codex PASS review (reference, not modified):** `docs/plans/2026-06-24-task-workbench-todo-lifecycle-codex-review.md`
- **Prior Claude review (this file, now overwritten):** `docs/plans/2026-06-24-task-workbench-todo-lifecycle-claude-review.md`
- **Dev log:** `docs/dev_log/2026-06-24-task-workbench-todo-lifecycle-prd.md`
- **Branch:** `docs/todo-lifecycle-prd` · **Base:** `release/sachima` @ `9694f0577`

Code anchors verified to exist (design-readiness sanity check only — read, not modified) so the PRD points the architect at real symbols:

- `AIAgent._hydrate_todo_store` → `run_agent.py:3355`; the actual resurrection write at `run_agent.py:3382` (`self._todo_store.write(last_todo_response, merge=False)`).
- Hydration trigger → `agent/turn_context.py:201-202` (`if conversation_history and not agent._todo_store.has_items(): agent._hydrate_todo_store(...)`).
- `TodoStore.format_for_injection` → `tools/todo_tool.py:125`; compression re-injection at `agent/conversation_compression.py:501`.
- Cached `_todo_store` → constructed `agent/agent_init.py:1107`, reused in `agent/agent_runtime_helpers.py:1814`, `agent/tool_executor.py:988`, and Gateway snapshot refresh `gateway/run.py:14815` (`_refresh_progress_todo_items`).
- `TransactionSnapshot` / `todo_items` → `gateway/progress/events.py`; clearing/normalization in `gateway/progress/store.py`, `gateway/progress/reader.py`, `gateway/progress/tracker.py`; Feishu + Web rendering in `gateway/progress/renderers.py`.
- Test homes exist: `tests/run_agent/test_run_agent.py` (hydration), `tests/tools/test_todo_tool.py` + `tests/tools/test_read_loop_detection.py` (`format_for_injection`), `tests/gateway/test_progress_tracker.py` and `tests/gateway/progress/`.

---

## VERDICT: PASS

Score rises from 94 to **95/100**. All prior Claude blockers and all three Codex blockers (B1 governance drift, B2 owner-scope, B3 agent hydration zombie path) are closed in the current PRD text. No critical auto-fail is triggered, no new P0/blocker is introduced, and every code path the PRD names is real and correctly identified. The PRD is design-ready as the basis for a later, separately-approved implementation packet under the existing non-approvals.

- Critical auto-fails: none triggered.
- Unresolved P0 / blockers: 0.
- Prior Claude blockers remaining: 0. Codex blockers remaining: 0.
- Pass threshold (`>=90`, no critical, no P0): met (95, clean).

---

## Score: 95 / 100

| # | Dimension | Max | Prior | Now | Rationale (delta) |
|---|-----------|----:|------:|----:|-------------------|
| 1 | Problem / outcome / user value | 15 | 14 | 14 | Unchanged. User value still framed qualitatively (less-confusing workbench), not a pain metric — non-blocking. |
| 2 | Scope, non-goals, explicit non-approvals | 15 | 15 | 15 | §3.1 governance reconciliation + §9 + §15 remain exhaustive and fail-closed; side-PRD boundary now explicit against P5/P6. |
| 3 | Actors, scenarios, edge cases | 15 | 14 | 14 | §4 adds reviewer/reader actors; §8.1 edge cases intact. |
| 4 | Functional + non-functional requirements | 15 | 14 | 15 | FR-11 closes the agent-side hydration gap with named paths and fail-closed semantics; §5.6 adds a concrete sanitized owner-scope model. |
| 5 | Measurable acceptance criteria / DoD | 20 | 19 | 19 | AC #7/#9/#10/#11/#13 span tracker/store/reader/renderer/run-agent/Feishu/Web; owner-scope isolation is test-mandated. |
| 6 | Constraints, dependencies, risks, open questions | 10 | 9 | 9 | §12 risk register covers owner-scope leakage and hydration resurrection; open questions appropriately scoped. |
| 7 | Traceability, terminology, internal consistency | 10 | 9 | 9 | Code anchors verified real; §5.5↔FR-5 enumeration nuance and alternate-path diagram shorthand remain minor non-blockers. |
| | **Total** | **100** | **94** | **95** | |

---

## Closed-blocker checklist (final re-check)

| Re-check item | Status | Evidence in PRD |
|---|---|---|
| **1. Deterministic explicit resume vs LLM/NL similarity** | **CLOSED** | §5.5 (PRD 109–121) requires an "explicit, deterministic resume signal" with a closed minimum-approved set; "Natural-language similarity alone must not decide that old TODOs are current"; ambiguity "must fail closed." FR-5 (257–267) restricts signals to exact/near-exact command forms, explicit references bound to exactly one suspended transaction, and renderer/dashboard actions, and forbids "Broad natural-language similarity, topic embedding, or LLM-only judgment." §8 NFR (331): "Deterministic display: FR-5 is authoritative; no hidden LLM-only state, broad semantic similarity, or transcript inference may decide that old TODOs are current." Consistent and authoritative. |
| **2. Governance reconciliation: docs-only side PRD vs P5 Temporal / P6 roadmap** | **CLOSED** | §3.1 (43–49) declares this a "docs-only side PRD gate" for the already-merged progress/TODO workbench that "does not replace, advance, or reinterpret the P5 Temporal/P6 runtime roadmap," lists the forbidden runtime/Gateway/Feishu-live/config/platform/restart/ingress/real-delivery surfaces, and states `docs/roadmap/current-status.md` "does not need to be updated" because phase authority / next approved runtime request is unchanged. Dev log (64–69) records the same patched scope. |
| **3. Same-owner-scope suspended hints/resume; sanitized `owner_scope_ref`; no raw platform IDs** | **CLOSED** | §5.6 (124–143) gates eligibility on all four components matching (active profile, platform/channel kind, conversation/chat/thread/topic scope, initiating user/sender scope); prohibits storing raw platform/chat/thread/topic/user IDs, card JSON, message payloads; defines `owner_scope_ref` as profile/platform labels + non-reversible digests/opaque refs; missing-ref records stay historical only; renderer/dashboard actions resume only after the backend re-verifies owner scope. FR-4 (253) persists `owner_scope_ref`; FR-6 (276) filters hint candidates by it; §8.1 (338) reaffirms the filter; AC #7 (385) mandates same-profile / different-user-chat-thread-topic isolation tests for see/hint/resume. |
| **4. Agent TODO hydration/re-injection path** | **CLOSED** | FR-11 (308–323) makes agent-side lifecycle correctness explicit, names `AIAgent._hydrate_todo_store()`, cached/fresh `_todo_store` reuse, and `TodoStore.format_for_injection()` across context compression, and requires fail-closed when the lifecycle marker is absent/ambiguous/other-owner/completed-archived (at most the FR-6 one-line hint). AC #9 (387) and AC #10 (388) require coverage of those paths after compression/restart and a transcript-history-pending-TODO + new-unrelated-request scenario producing an empty main block. Verified real: the named symbols and the resurrection write (`run_agent.py:3382`) and compression re-injection (`conversation_compression.py:501`) exist as described. |
| **5. Testable acceptance criteria across tracker/store/reader/renderer/run_agent/Feishu/Web/API** | **CLOSED** | §10 lists 14 pass/fail-decidable criteria; AC #8 (reader/store/tracker survive missing fields / malformed JSONL / rotation / restart), AC #9 (run-agent hydration + cached store + injection), AC #11 (Feishu + Web/API same semantics + owner-scope isolation), AC #13 ("tracker/store/reader/renderer/run-agent hydration integration, not only pure helper functions"), AC #12 (redaction regression). §8 NFR "Evidence-first" reinforces test-before-readiness. |
| **6. Non-approvals: no implementation / live / Gateway lifecycle / restart / platform / config / real delivery** | **CLOSED** | §3.1 (47), §9 (362–373), and §15 (461–465, future phrase explicitly "not yet granted") keep all implementation, Gateway restart/reload, production config, live/default-on rollout, platform adapter mutation, new model tools, broad transcript inference, and raw log/secret/platform-ID persistence un-approved. The future approval phrase scopes any later grant to progress/workbench/TODO-lifecycle code+tests while still forbidding Gateway lifecycle/live/config/platform changes. |

---

## Non-blocking notes (carry into technical design, not gating)

- **N1 — §5.5 vs FR-5 resume-signal enumeration.** §5.5 enumerates {explicit resume command; explicit reference incl. renderer button; already-active same-task transaction}; FR-5 enumerates {exact/near-exact command forms; explicit references bound to one suspended transaction; renderer/dashboard action carrying a transaction id}. The lists overlap but categorize the renderer action and the already-active case differently. Not contradictory; design should collapse them into one canonical signal list to prevent divergent implementations.
- **N2 — "near-exact command forms" tolerance.** §5.5/FR-5 permit "near-exact" matching. Acceptable at PRD altitude, but the design must pin the concrete deterministic string/pattern set (and keep it a literal/regex match, not a model judgment) so the FR-5 / §8 deterministic-display invariant survives implementation. Codex flagged the same item.
- **N3 — Alternate-path lifecycle diagram shorthand.** §11 still writes `active → blocked / waiting_user / waiting_external / failed_recoverable → suspended`, reading reasons as if they were states. FR-2 (209–229) and the §11 display table correctly separate lifecycle state from suspension reason, so this is readable transition shorthand; normalize it in the technical design. (Matches Codex non-blocking note.)
- **N4 — Authority bullet vs governance prose.** The authority bullet at §3 (line 34) summarizes only the machine status block from `current-status.md`; the §3.1 reconciliation immediately below carries the human-authored P5 PR B boundary. No blocker.
- **N5 — User-value success signal (carried, optional).** §1 could state a one-line success metric (e.g., "next unrelated request renders zero inherited TODOs in the main block"); AC #5 already effectively encodes it. Non-blocking.

None of N1–N5 gates design; all are early-design tightenings.

---

## Design-readiness conclusion

The revised PRD is **design-ready in governance, product semantics, and decision content.** The three Codex blockers are closed in the PRD text: (B1) the roadmap boundary is reconciled — this is an explicit docs-only side gate that neither advances nor rewrites P5 Temporal / P6 authority and requires no status update; (B2) suspended-work hints and resume are confined to a sanitized same-owner scope with a defined `owner_scope_ref` (labels + non-reversible digests/opaque refs) and an explicit prohibition on raw platform/chat/thread/topic/user IDs, backed by isolation tests; (B3) the agent-side hydration/re-injection zombie path is now a required acceptance gate naming the exact real code paths (`AIAgent._hydrate_todo_store`, cached `_todo_store`, `TodoStore.format_for_injection`) with fail-closed semantics across compression/restart. The earlier Claude P0 (deterministic resume vs deterministic-display) and B2/B3 testability gaps remain closed. Acceptance criteria are pass/fail-decidable and span tracker/store/reader/renderer/run-agent/Feishu/Web/API. All cited code anchors verify as real, so the PRD will not send the architect to phantom symbols.

This re-review confirms the Codex `VERDICT: PASS` and adds no new blocker. No further Claude blocker re-review is required to clear the bar.

**Recommended path:** proceed to Hermes's final user-facing solution packet and explicit user approval per §14, folding N1–N5 in as early-design tightenings. No implementation, Gateway/live/config/platform, or roadmap authority is granted by this review.

- **PRD reviewed:** `docs/plans/2026-06-24-task-workbench-todo-lifecycle-prd.md`
- **Branch reviewed:** `docs/todo-lifecycle-prd` (base `release/sachima` @ `9694f0577`)
- **VERDICT: PASS** — 95/100, all prior Claude and Codex blockers closed, no critical/P0.
