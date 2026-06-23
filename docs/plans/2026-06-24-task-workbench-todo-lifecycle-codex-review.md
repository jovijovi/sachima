# Codex PRD Re-Review - Task Workbench TODO Lifecycle

Role: primary independent reviewer for governed Sachima/Hermes PRD gate.
Mode: blocker-only re-review after Hermes patched the prior Codex blockers.
Branch: `docs/todo-lifecycle-prd`
Base: `release/sachima` at `9694f0577`
Date: 2026-06-24

VERDICT: PASS

Score: 94 / 100

## Reviewed Paths

- `AGENTS.md` instructions provided in prompt and repository copy
- `GOAL.md`
- `docs/roadmap/current-status.md`
- `docs/plans/2026-05-11-sachima-final-goal-phase-development-plan.md`
- `docs/plans/2026-06-24-task-workbench-todo-lifecycle-prd.md`
- `docs/plans/2026-06-24-task-workbench-todo-lifecycle-claude-review.md`
- `docs/dev_log/2026-06-24-task-workbench-todo-lifecycle-prd.md`
- `run_agent.py`
- `tools/todo_tool.py`
- `gateway/run.py`
- `gateway/progress/events.py`
- `gateway/progress/tracker.py`
- `gateway/progress/store.py`
- `gateway/progress/reader.py`
- `gateway/progress/renderers.py`
- Relevant TODO/progress tests under `tests/run_agent/`, `tests/tools/`, and `tests/gateway/`

Preflight note: the AGENTS-requested `phase-gate-drift-control` skill is not available in the active Codex skill set or filesystem skill search. I applied the roadmap preflight manually.

## Roadmap Preflight

Current mainline phase position: P5 Temporal production runtime enablement Slice 1 design/readiness PR A is merged; the current mainline candidate remains docs-only P5 Temporal PR B pre-development governance.

Next allowed mainline request: PR B pre-development governance only, then a separately approved PR B implementation request if that gate passes.

Explicit non-approvals preserved: no PR B implementation by this PRD, no Temporal/Worker start, no workflow/activity execution, no acpx/npx/agent invocation, no production cluster/traffic, no P6 real agent execution, no write roles, no Gateway-owned lifecycle, no Gateway/Feishu/live behavior, no production config write, no platform mutation, and no real delivery.

Open tails considered: PE-1D default-port WATCH, P4 envelope cross-repo NEXT_PHASE, roadmap status-dashboard WATCH, controlled AI FLOW real-execution NEXT_PHASE, WP3b active-run cancellation WATCH, and open P5 Temporal PR B NEXT_PHASE.

Allowedness: this Task Workbench TODO Lifecycle PRD is allowed as a docs-only side PRD/review gate because it does not alter roadmap phase authority, runtime approvals, service lifecycle, live behavior, Gateway/Feishu delivery, platform adapters, or config.

## Closed-Blocker Checklist

| Prior blocker | Status | Evidence in revised PRD/dev log |
|---|---|---|
| B1 - governance drift | CLOSED | The PRD now states this is a **docs-only side PRD gate** for the already-merged progress/TODO workbench, not P5 Temporal PR B, and it does not replace or advance the P5/P6 roadmap (`docs/plans/2026-06-24-task-workbench-todo-lifecycle-prd.md:43-49`). It explicitly denies implementation/runtime authority and names the forbidden Temporal/Worker, controlled AI FLOW, agent/acpx/npx, Gateway/Feishu live, production config, platform mutation, restart/reload, public ingress, and real-delivery surfaces (`...prd.md:45-49`). The dev log records the same patched scope (`docs/dev_log/2026-06-24-task-workbench-todo-lifecycle-prd.md:64-69`). |
| B2 - suspended-work hint/resume candidate scope | CLOSED | The PRD now requires same safe owner scope for hint/resume eligibility: active Hermes profile, platform/channel kind, conversation/chat/thread/topic scope, and initiating user/sender scope (`...prd.md:123-143`). It prohibits raw platform/chat/thread/topic/user IDs and defines sanitized `owner_scope_ref` digests/opaque refs (`...prd.md:132-143`). FR-6 filters hint candidates by matching `owner_scope_ref` (`...prd.md:269-279`), and AC #7 requires same-profile but different user/chat/thread/topic isolation tests for see/hint/resume (`...prd.md:381-386`). |
| B3 - agent TODO hydration/re-injection zombie path | CLOSED | FR-11 now makes agent-side TODO lifecycle correctness explicit, including deterministic lifecycle markers for current, suspended, completed/archived, and unrelated clean state (`...prd.md:308-323`). It names `AIAgent._hydrate_todo_store()`, cached/fresh agent `_todo_store` reuse, and `TodoStore.format_for_injection()` as required design paths (`...prd.md:317-323`). AC #9-10 require coverage for those paths after context compression/restart and an old pending TODO in transcript history without injecting it into a new unrelated main task (`...prd.md:387-388`). |

## Remaining Blockers

None.

## Non-Blocking Notes

- Lifecycle state/reason consistency is now acceptable. FR-2 distinguishes lifecycle states from suspension reasons (`...prd.md:209-229`), and the display table is labeled `Lifecycle state / reason` (`...prd.md:421-431`). The alternate-path diagram still writes `active -> blocked / waiting_user / waiting_external / failed_recoverable -> suspended` (`...prd.md:403-409`), which is readable as transition shorthand but should be normalized in the technical design.
- `near-exact command forms` remain a design-tightening item. The PRD correctly forbids broad similarity, embeddings, and LLM-only judgment (`...prd.md:261-267`, `...prd.md:331`), but the later design should pin the exact deterministic string/pattern set.
- The future approval phrase now allows progress/workbench/TODO lifecycle code and tests while forbidding Gateway service lifecycle/restart/platform/live/config changes (`...prd.md:461-465`). That resolves the prior over-broad "no Gateway changes" concern.
- The local Hermes skill references are no longer presented as repository authority (`...prd.md:36-41`). `multi-intent-planning` is present only under `prototypes/flowweaver_phase3/...`, and `hardening-user-facing-progress-displays` was not found in this environment, but the PRD clearly labels both as non-repo authoring inputs, so this is not blocking.
- The authority bullet at `...prd.md:34` still summarizes only the machine block from `current-status.md`; the new governance reconciliation immediately below covers the human-authored P5 PR B boundary. No blocker.

## Design-Readiness Conclusion

The revised PRD is design-ready for the next docs-only solution packet and later explicit implementation approval. The prior blockers are closed: roadmap authority is reconciled, suspended work is scoped to sanitized same-owner boundaries, and the known agent TODO hydration/compression zombie path is now a required acceptance gate. No new critical/P0 blocker was found.
