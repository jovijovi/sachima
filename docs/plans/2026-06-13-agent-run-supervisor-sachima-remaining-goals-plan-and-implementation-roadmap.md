
# Sachima × agent-run-supervisor Remaining Goals Plan and Implementation Roadmap

Date: 2026-06-13
Base branch: `release/sachima` at `3e71cb77625882d1ac51c73b50b695da98b55750`
Planning branch: `docs/agent-run-supervisor-remaining-goals-plan`
Status: `docs_only_planning_gate_codex_review_passed` (not implementation approval)

## Hermes final arbitration

Hermes decision: **ACCEPT** the Claude Code architect plan with **Codex CLI primary blocker review PASS**: `VERDICT: PASS` / `BLOCKERS: None`.

This document is a planning/design artifact only. It records the remaining target sequence after Phase E-2 and recommends the smallest safe next implementation PR, but it does **not** approve any implementation, execution, additional `acpx` invocation, live behavior, Gateway/Feishu work, production config write, service restart, platform adapter mutation, or real delivery.

### Agent review chain

- Claude Code role: architect / documentation engineer. Output: remaining-goals roadmap draft; no repo file edits, no commits, no pushes, no service/runtime actions.
- Codex CLI role: blocker-only reviewer. First attempt failed because the read-only sandbox could not inspect files; Hermes reran review with embedded draft + authority excerpts and no tool usage. Final result: `VERDICT: PASS`, `BLOCKERS: None`.
- Hermes role: PM/controller/verifier/repo operator; final arbitration and document landing.

### Mandatory clarification adopted from review

WP1a and WP1b stay visibly separate:

- **WP1a**: Claude Code read-only role + capability-gate extension with injected fakes only; no real smoke.
- **WP1b**: one bounded real read-only Claude Code smoke; requires a separate future approval.

The next safe mainline request is WP1a only.

---

## Claude Code architect plan adopted by Hermes

> **For Hermes:** This is a **PLANNING / DESIGN gate only**. It incorporates a Claude Code architect draft;  it does not commit, push, open PRs, merge, run any local execution/session/cancellation, or start any service/CLI/`acpx`/`npx`/Gateway/Feishu surface. Merging this document approves **nothing** beyond recording the plan. Every work package below requires its own separately named approval before any code or execution. This document is the landed planning artifact for the remaining-goals roadmap; it still approves no implementation or execution.

**Date:** 2026-06-13
**Base branch:** `release/sachima`
**Author role:** Claude Code = architect + documentation engineer (docs only)
**Review chain intended:** Hermes (PM/controller/verifier/repo operator/evidence arbiter) → this draft → **Codex CLI primary blocker review** → Hermes user review packet → owner approval → land.

## Status markers

```text
PLANNING_DESIGN_ONLY
IMPLEMENTATION_NOT_APPROVED
EACH_WORK_PACKAGE_NEEDS_ITS_OWN_APPROVAL
LOCAL_OFFLINE_DEFAULT_OFF_UNTIL_SEPARATELY_APPROVED
CLAUDE_CODE_NOT_YET_CONNECTED_FROM_SACHIMA
NO_LIVE
NO_GATEWAY
NO_FEISHU
NO_REAL_DELIVERY
NO_PRODUCTION_CONFIG
NO_CANCELLATION_EXECUTION
NO_CONTROLLED_AI_FLOW_EXECUTION
NO_WRITE_CAPABLE_ROLES
NO_UNBOUNDED_PERSISTENT_SESSIONS
```

---

## 1. Title

**agent-run-supervisor × Sachima — Remaining-Goals Plan & Implementation Roadmap (Post Phase E-2 bounded real persistent-session execution).**

A staged, default-off, local/offline-first roadmap that carries the supervisor → Sachima mainline from "one bounded Codex persistent session" to the `GOAL.md` end-state (a safe, durable, recoverable IM AI workbench), with one separately approved gate per increment and no premature jump to live delivery.

---

## 2. Current baseline in plain language

Where the mainline actually is today (verified against `current-status.md`, the Phase E/E-2 docs, and the Phase C implementation doc):

- **Shape of what exists.** Sachima/FlowWeaver owns a caller-side, **default-off, local/offline** seam into `agent-run-supervisor`. The supervisor is an independent local library; the **Gateway is excluded** as caller/renderer/delivery surface; **Feishu/IM is excluded entirely**. Nothing is live, nothing default-on.
- **What is actually proven to run.**
  - **Phase D:** exactly **one** host-local **read-only Codex one-shot** through pinned local `acpx 0.10.0` — execution pipeline PASS, business verdict PASS, replay produced no duplicate, no leftover processes, evidence stored **outside** the repo.
  - **Phase E-2:** exactly **one** bounded **persistent session lifecycle** — `create → one read-only turn → close` — driven by a real `SessionRuntime`, default-off, fail-closed, CI-safe, pinned local `acpx` only, evidence outside the repo, Codex blocker-only re-review PASS.
- **The engine matrix is Codex-only.** The single runnable role is `sachima.codex.primary_reviewer` (read/search only). The capability gate **fails closed on any non-`codex` adapter** and on any write/execute/terminal capability. **There is no Claude Code role on the Sachima side, and no Claude Code path has ever been exercised from Sachima.** Claude Code role keys (`sachima.claude.architect`, `sachima.claude.main_programmer`, `sachima.claude.docs_engineer`) are documented as **future labels only, not runnable**.
- **What is designed but not executable.** Multi-turn semantics, `session_abort`, and the full cancellation model (request record vs. execution) are **designed** (Phase E design packet) and partially **state-machined with injected fakes** (PR #125), but: only a **single** real turn has run; **cancellation execution is not approved and has no supervisor-side interrupt API**; the claim store is a single **in-process** mutex (no cross-process durable adapter).
- **Standing non-approvals still in force.** No live/default-on; no Gateway involvement/mutation/restart; no Feishu/IM/public ingress; no real delivery/ACK; no production config writes/service restarts/platform-adapter mutation; no controlled AI FLOW execution; no cancellation execution; no additional/unbounded persistent sessions beyond the proven bounded lifecycle; no write-capable Claude/Codex roles; no Satine/Hermes-profile ACP execution; no `npx`/network-fetch runnable path.

**Plain-language summary:** we have proven, twice, that a single bounded **read-only Codex** task can run safely through a fail-closed local seam — once as a one-shot, once as a one-turn persistent session. Everything else (a second engine, many turns, stopping work, multi-step orchestration, writing files, durable runtime, real delivery) is still on paper or behind injected fakes.

---

## 3. Target end-state

The `GOAL.md` north star decomposed into three concentric rings. Each ring is fully reached before the next is *enabled*, though design for the next may proceed in parallel.

### 3.1 Ring A — Local/offline engineering-agent loop (nearest)

A host-local, default-off, multi-engine **read-only** agent loop usable as an engineering assistant:

- Both **Codex CLI** and **Claude Code** available as **read-only** roles through the identical fail-closed seam, capability-gated, pinned-runner-only.
- **Bounded multi-turn** persistent sessions (N turns, explicit budgets, bounded lifetime, graceful close and operator-gated forced `session_abort`), with proven cleanup and no orphaned processes.
- **Cancellation execution** that can actually interrupt an in-flight local turn and prove cleanup, idempotently and fail-closed.
- All durable state remains claim-checked/sanitized; all evidence outside the repo; still **no write capability, no orchestration, no delivery**.

**Done when:** an operator can locally run either engine, hold a bounded multi-turn read-only session, stop it cleanly mid-turn, and replay without duplication — entirely offline, default-off.

### 3.2 Ring B — Controlled AI FLOW runtime (middle)

A caller-owned, still **local/offline** orchestration layer that chains roles into a real workflow:

- **Controlled AI FLOW orchestration**: multi-role, multi-step task graphs (e.g. architect → programmer → reviewer) executed over the seam, with FlowWeaver owning transaction/operation/session/turn state, retries, idempotency, and per-step operator gates.
- **Write-capable roles** introduced behind mandatory **diff-review + rollback** gates, confined to a sandboxed scratch workspace outside any production tree, never auto-applied.
- **Durable runtime integration**: a caller-supplied durable backend (Temporal or equivalent) and a **cross-process** transactional claim store replace the in-process mutex, giving recoverable execution, retry, query, update, and rollback — **without** the Gateway or a Worker owning the runtime lifecycle.

**Done when:** a long, multi-step AI FLOW task runs to completion locally, survives a process restart mid-flow, can be rolled back, and leaks nothing into durable state — still offline, still no real delivery.

### 3.3 Ring C — Later live / Gateway / Feishu delivery (farthest)

The full `GOAL.md` IM workbench, reached only after Rings A and B are production-hardened and **each** delivery axis is separately approved:

- Controlled external **Sachima ingress** (Envelope v1, HMAC/schema/no-leak proven cross-repo).
- **Gateway** as the rendering/delivery/ACK boundary — explicitly owned, never silently mutating Temporal/Worker/socket/subprocess lifecycle.
- **Feishu/IM real delivery** of sanitized final text, rich cards, progress cards, media, and ACKs as **separate tracked surfaces**, behind a limited, reversible pilot.

**Done when:** a real IM request runs a durable AI FLOW task and delivers sanitized results back through the channel, surviving restarts/retries/duplicates/rollback, with raw material kept out of durable history and user-visible evidence.

**Hard ordering rule:** no Ring C axis is enabled before its Ring A/B prerequisites are proven and its own delivery-axis approval is named. Fake-send success, loopback ingress, and HTTP 2xx ACKs do **not** approve real delivery.

---

## 4 & 5. Remaining work packages (recommended order, with full per-package detail)

Seven work packages, ordered by dependency and risk. WP1 is the recommended immediate next step (see §6). Each package is a **separate approval**; none is authorized by this document.

---

### WP1 — Claude Code read-only role + bounded smoke

**Goal.** Prove a **second engine** works through the exact same fail-closed seam: add a read-only **Claude Code** role and extend the capability gate to admit a read-only `claude` adapter, then (separately) run one bounded read-only Claude Code smoke. This is the first Claude Code presence on the Sachima side.

**Scope.** Split into two sub-gates mirroring the proven Phase C→Phase D rhythm:
- **WP1a (implementation, injected fakes only):** a committed, non-runnable read-only Claude Code role config (`adapter_agent: claude`, `acpx_binary: null`, read/search only); a minimal, explicit extension of the `exec_controlled` (and/or session) capability gate to allow a read-only `claude` adapter while still rejecting every write/execute/terminal/fetch/mode-switch capability; pinned-runner provenance discipline reused unchanged; tests with injected fakes; self-test smoke wiring. **No real smoke.**
- **WP1b (one bounded real smoke):** exactly one host-local read-only Claude Code run (one-shot or one-turn), pinned local runner only, evidence outside the repo, replay-no-duplicate proof.

**Explicit non-approvals.** No write capability; no persistent **unbounded** sessions; no multi-turn beyond the single proven turn (until WP2); no cancellation execution; no orchestration; no `npx`/network-fetch runner; no Satine/Hermes-profile ACP; no live/Gateway/Feishu/production config/real delivery. WP1a approves **no** real execution.

**Files likely touched.**
```text
sachima_supervisor/roles/claude_code_read_only_reviewer_v1.json        (new; acpx_binary/runner null; not runnable)
sachima_supervisor/activity_controlled_exec.py                          (capability gate: admit read-only claude adapter)
sachima_supervisor/activity_session_real_execution.py                   (only if the smoke is a session turn; adapter allowlist)
sachima_supervisor/__init__.py                                          (exports, if any)
tests/sachima_supervisor/test_activity_controlled_exec.py              (claude read-only admit + write/non-claude reject)
tests/sachima_supervisor/test_claude_code_read_only_role.py            (new; capability + no-leak + forbidden-surface)
scripts/sachima_claude_code_read_only_smoke.py                          (new; --self-test parity; real mode pinned-runner)
docs/plans/... + manifest + docs/dev_log/... + docs/roadmap/current-status.md
```

**Tests / evidence required.**
- RED-first new tests; capability gate **admits** the read-only `claude` adapter and **still rejects** any write/execute/terminal/fetch capability and any non-`{codex,claude}` adapter.
- No-leak tests: durable projection stores only stable codes/refs/digests/counts — never raw prompt/output/tool output/exception text.
- Forbidden-surface scan over the new source (no Gateway/Feishu/webhook/`npx -y`/subprocess-launcher/socket/service-restart).
- Full `tests/sachima_supervisor` suite stays green; `compileall`; `git diff --check`; `codegraph status`.
- **WP1b only:** one real smoke summary + post-verify + final validation outside the repo; exactly one run; no leftover Claude/runner processes; `final_message_persisted=false`.
- Codex CLI primary blocker re-review `VERDICT: PASS` / `BLOCKERS: None`.

**Acceptance criteria.** A read-only Claude Code role is committed and non-runnable by construction; the gate change is the **minimal** admit-one-read-only-adapter delta with adversarial reject tests; WP1a runs no real engine; WP1b (if approved) proves exactly one bounded read-only Claude Code run with sanitized out-of-repo evidence and replay-no-duplicate; all standing non-approvals hold; status dashboard updated.

**Suggested approval phrases.**
```text
# WP1a
approve_agent_run_supervisor_sachima_claude_code_read_only_role_capability_extension_local_offline_implementation_injected_fakes_only_no_real_smoke_no_write_roles_no_live_no_gateway_no_feishu_no_production_config_no_real_delivery
# WP1b
approve_agent_run_supervisor_sachima_claude_code_read_only_bounded_real_local_smoke_pinned_local_runner_only_single_run_no_unbounded_no_cancellation_no_write_roles_no_live_no_gateway_no_feishu_no_production_config_no_real_delivery
```

---

### WP2 — Multi-turn persistent session hardening

**Goal.** Generalize the Phase E-2 single-turn lifecycle to a **bounded N-turn** read-only session with enforced budgets, bounded lifetime, graceful close, operator-gated forced `session_abort`, and proven cleanup — using the records/guards already designed in the Phase E packet.

**Scope.** Drive `create → N bounded read-only turns → close` (and the `session_abort` forced-terminal path) for read-only roles (Codex and, post-WP1, Claude Code); enforce `max_turns`, `max_artifacts`, evidence-size, and lifetime budget markers (`activity_budget_exceeded`); single in-flight turn invariant; lease-internal open-state recheck on every send; lifecycle guard on close/abort; full race regression suite (send-vs-send, send-vs-close/abort, close-vs-close, abort-vs-abort, lease steal during in-flight turn, finalize-time CAS). Real bounded execution permitted; still single in-process claim store (cross-process is WP6).

**Explicit non-approvals.** No cancellation **execution** mid-turn (WP3); no write roles; no orchestration/AI FLOW; no unbounded/indefinite sessions; no `npx`/network runner; no live/Gateway/Feishu/production config/real delivery.

**Files likely touched.**
```text
sachima_supervisor/activity_session_lifecycle.py            (budget enforcement, multi-turn invariants, abort path)
sachima_supervisor/activity_session_real_execution.py       (N-turn bounded real wiring; bounded-lifetime guard)
sachima_supervisor/roles/session_worker_persistent_v1.json  (budget markers; still read-only, runner null)
tests/sachima_supervisor/test_activity_session_lifecycle.py (multi-turn + budgets + race regressions)
tests/sachima_supervisor/test_activity_session_real_execution.py (bounded N-turn real-path tests w/ fakes)
scripts/sachima_phase_e2_persistent_session_smoke.py        (extend to bounded N turns + abort)
docs/plans/... + manifest + dev_log + current-status.md
```

**Tests / evidence required.** Race regression suite with a lock-removal mutation check proving the tests depend on the lock; budget-exceeded fail-closed tests; abort-records-intent-before-terminal test; idempotent replay across turns; no-leak across turn evidence; one bounded **real** multi-turn smoke (out-of-repo evidence) showing exactly N turns, one supervisor session, clean close, no leftover processes; Codex blocker re-review PASS.

**Acceptance criteria.** A bounded multi-turn read-only session runs and closes cleanly; every budget bound fails closed; forced `session_abort` records intent first and reaches a single terminal state; all races fail closed or resolve to a single correct outcome; no orphaned processes; durable state leak-free; dashboard updated.

**Suggested approval phrase.**
```text
approve_agent_run_supervisor_sachima_bounded_multi_turn_persistent_session_hardening_local_offline_pinned_runner_only_read_only_roles_only_no_cancellation_execution_no_write_roles_no_controlled_ai_flow_no_unbounded_sessions_no_live_no_gateway_no_feishu_no_production_config_no_real_delivery
```

---

### WP3 — Cancellation execution

**Goal.** Turn the designed cancellation **request record** into real, fail-closed cancellation **execution**: actually interrupt an in-flight local turn/session and **prove cleanup**, idempotently and operator-gated. (`execute_real_cancellation` currently refuses unconditionally with `activity_cancel_not_approved`.)

**Scope.** Two strict sub-gates:
- **WP3a (supervisor interrupt API design + the request-state implementation):** define and document a testable supervisor-side session/run interrupt API with stable sanitized result semantics (none exists today), and implement the `CancellationRequestRecord` lifecycle (`cancel_requested → cancelled | cancel_failed | cancel_ambiguous`) with operator gate, lease/epoch binding, and idempotency — **still no real interrupt fired**.
- **WP3b (bounded cancellation execution):** fire exactly one real interrupt against a bounded read-only session and assert cleanup (no leftover child processes / temp/session dirs / leases), with cancel-vs-send / cancel-vs-close / cancel-vs-cancel / cancel-during-finalize / cancel-vs-lease-steal regression tests; ambiguous outcomes fail closed (`activity_cancel_ambiguous`), never duplicate-interrupt.

**Explicit non-approvals.** No write roles; no orchestration; no auto/agent-initiated cancellation (operator gate mandatory); no `npx`/network runner; no live/Gateway/Feishu/production config/real delivery. WP3a fires no real interrupt.

**Files likely touched.**
```text
sachima_supervisor/activity_session_lifecycle.py            (request-state already present; finalize integration)
sachima_supervisor/activity_session_real_execution.py       (execute_real_cancellation: replace refusal w/ gated path)
sachima_supervisor/local_offline.py                         (seam: add a guarded cancel/interrupt mode — new label)
tests/sachima_supervisor/test_activity_session_real_execution.py (cancel races + cleanup proof)
tests/sachima_supervisor/test_cancellation_execution.py     (new)
scripts/sachima_cancellation_smoke.py                       (new; bounded interrupt + post-cleanup assertion)
docs/plans/... + manifest + dev_log + current-status.md
```

**Tests / evidence required.** Post-cancel "no leftover acpx/runner/child processes" assertion (generalized from Phase D); idempotent cancel-after-close / close-after-cancel / cancel-after-cancel collapse to one terminal; finalize-CAS-on-stale-epoch fail-closed; ambiguous-state held fail-closed; one bounded real cancellation smoke with out-of-repo evidence; Codex blocker re-review PASS.

**Acceptance criteria.** A real in-flight read-only turn can be interrupted under an operator gate; cleanup is verified; every cancel race fails closed or yields a single terminal; ambiguity never triggers a duplicate interrupt or relaunch; a second interrupt signal is structurally impossible; dashboard updated.

**Suggested approval phrases.**
```text
# WP3a
approve_agent_run_supervisor_sachima_cancellation_request_state_and_supervisor_interrupt_api_design_local_offline_no_real_interrupt_no_live_no_gateway_no_feishu_no_production_config_no_real_delivery
# WP3b
approve_agent_run_supervisor_sachima_bounded_cancellation_execution_local_offline_with_cleanup_proof_operator_gated_read_only_sessions_only_no_write_roles_no_live_no_gateway_no_feishu_no_production_config_no_real_delivery
```

---

### WP4 — Controlled AI FLOW local/offline orchestration

**Goal.** Introduce the first **controlled AI FLOW**: a caller-owned, local/offline multi-role / multi-step task graph (e.g. architect → programmer-candidate(read-only) → reviewer) executed over the seam, with FlowWeaver owning all durable state, per-step idempotency, retries, and per-step operator gates.

**Scope.** Design gate first (orchestration semantics: step graph, inter-step claim-check artifact passing, per-step role binding, retry/compensation, fail-closed step ambiguity), then a local/offline orchestration implementation restricted to **read-only roles only** and bounded step counts. Builds on WP1–WP3 (multi-engine, multi-turn, stoppable).

**Explicit non-approvals.** No write roles in the first AI FLOW slice (deferred to WP5); no agent-to-agent auto-routing / `@all` fan-out / automatic replies / worker auto-routing; no durable-runtime ownership change (WP6); no live/Gateway/Feishu/production config/real delivery.

**Files likely touched.**
```text
sachima_supervisor/activity_ai_flow_orchestration.py        (new; step graph + per-step claim/CAS)
sachima_supervisor/activity_session_lifecycle.py            (reuse session/turn records per step)
sachima_supervisor/roles/*.json                             (read-only role keys per step)
tests/sachima_supervisor/test_ai_flow_orchestration.py      (new; step ordering, retry, fail-closed, no-leak)
scripts/sachima_ai_flow_local_smoke.py                      (new; bounded multi-step read-only flow)
docs/plans/... (design packet first) + manifest + dev_log + current-status.md
```

**Tests / evidence required.** Step-ordering and dependency tests; per-step idempotency/retry/compensation; inter-step artifacts passed only as claim-check refs/digests; fail-closed on any ambiguous step; no-leak across the whole flow; one bounded local read-only multi-step smoke (out-of-repo evidence); Codex blocker re-review PASS on both the design and the implementation slice.

**Acceptance criteria.** A bounded multi-step read-only flow runs end-to-end locally, is resumable/idempotent per step, passes only sanitized refs between steps, fails closed on any step ambiguity, and leaks nothing; dashboard updated.

**Suggested approval phrases.**
```text
# WP4 design
approve_agent_run_supervisor_sachima_controlled_ai_flow_local_offline_orchestration_design_docs_only_no_implementation_no_write_roles_no_live_no_gateway_no_feishu_no_production_config_no_real_delivery
# WP4 implementation
approve_agent_run_supervisor_sachima_controlled_ai_flow_local_offline_orchestration_implementation_read_only_roles_only_bounded_steps_no_write_roles_no_auto_routing_no_live_no_gateway_no_feishu_no_production_config_no_real_delivery
```

---

### WP5 — Write-capable roles with review/rollback gates

**Goal.** Allow roles to **write** (edit files / produce applied diffs) for the first time, confined to a **sandboxed scratch workspace** outside any production tree, behind a **mandatory human diff-review gate** and a proven **rollback** mechanism. Nothing is ever auto-applied.

**Scope.** Design gate first (write-capability model, sandbox boundary, diff capture, review gate, rollback/compensation semantics, blast-radius limits), then implementation: write-capable Claude/Codex role configs gated by a new capability flag; all writes land in an isolated workspace (e.g. dedicated git worktree) and require explicit operator approval before any propagation; full rollback proof.

**Explicit non-approvals.** No writes to any production/source tree, the Gateway, configs, or platform adapters; no auto-apply / auto-merge; no live/Gateway/Feishu/production config/real delivery; write roles remain local/offline and sandboxed.

**Files likely touched.**
```text
sachima_supervisor/activity_controlled_exec.py / activity_session_real_execution.py  (write-capability flag + sandbox enforcement)
sachima_supervisor/roles/claude_code_write_capable_sandboxed_v1.json   (new; explicit write flag; sandboxed root)
sachima_supervisor/roles/codex_write_capable_sandboxed_v1.json         (new)
sachima_supervisor/workspace_sandbox.py                                 (new; isolated workspace + rollback)
tests/sachima_supervisor/test_write_capable_roles.py                   (new; sandbox escape attempts fail closed)
scripts/sachima_write_role_sandboxed_smoke.py                          (new; write → review gate → rollback)
docs/plans/... (design first) + manifest + dev_log + current-status.md
```

**Tests / evidence required.** Sandbox-escape attempts (path traversal, absolute paths, symlink escape) fail closed; diffs captured as sanitized artifacts; no write proceeds without the explicit review gate; rollback restores the sandbox to its pre-write state and is verified; no-leak on diff evidence; bounded local smoke (out-of-repo evidence); Codex blocker re-review PASS on design and implementation.

**Acceptance criteria.** A write-capable role can produce changes only inside the isolated sandbox, never auto-applied, always reviewable, fully rollback-provable; every escape attempt fails closed; dashboard updated.

**Suggested approval phrases.**
```text
# WP5 design
approve_agent_run_supervisor_sachima_write_capable_role_sandboxed_with_review_and_rollback_design_docs_only_no_implementation_no_production_tree_writes_no_live_no_gateway_no_feishu_no_production_config_no_real_delivery
# WP5 implementation
approve_agent_run_supervisor_sachima_write_capable_role_local_offline_sandboxed_workspace_only_with_mandatory_review_gate_and_rollback_proof_no_auto_apply_no_production_tree_writes_no_live_no_gateway_no_feishu_no_production_config_no_real_delivery
```

---

### WP6 — Durable runtime integration

**Goal.** Replace the in-process mutex claim store with a caller-supplied **durable runtime** (Temporal or equivalent) and a **cross-process transactional claim store**, giving recoverable execution, retry, query, update, and rollback — **without** the Gateway or a Worker silently owning the runtime lifecycle.

**Scope.** Design gate first (durable Activity contract, cross-process claim-store adapter, restart-recovery semantics, query/update/signal mapping, lease/epoch durability), then a local durable backend behind the seam with the same fail-closed guards; prove a flow survives a mid-execution process restart and resumes idempotently.

**Explicit non-approvals.** No Gateway-owned / Worker-owned Temporal lifecycle; no production runtime/service start by the Gateway; no live/Gateway/Feishu/production config/real delivery; durable runtime stays caller-owned and local until a separate live gate.

**Files likely touched.**
```text
sachima_supervisor/durable_claim_store.py                  (new; cross-process transactional CAS adapter)
sachima_supervisor/activity.py / activity_controlled_exec.py / activity_session_lifecycle.py  (durable-store seam)
sachima_supervisor/durable_runtime_adapter.py              (new; caller-supplied runtime contract)
tests/sachima_supervisor/test_durable_claim_store.py       (new; cross-process CAS + restart recovery)
scripts/sachima_durable_runtime_restart_smoke.py           (new; kill-and-resume proof)
docs/plans/... (design first) + manifest + dev_log + current-status.md
```

**Tests / evidence required.** Cross-process concurrent claim tests (exactly-once under contention); kill-mid-flow then resume-idempotent proof; query/update/rollback against durable state; no-leak in durable records; one local restart-recovery smoke (out-of-repo evidence); Codex blocker re-review PASS on design and implementation.

**Acceptance criteria.** A flow survives a process kill and resumes without duplication or leak; the claim store is cross-process exactly-once; the Gateway owns no runtime lifecycle; dashboard updated.

**Suggested approval phrases.**
```text
# WP6 design
approve_agent_run_supervisor_sachima_durable_runtime_integration_caller_owned_cross_process_claim_store_design_docs_only_no_gateway_owned_lifecycle_no_implementation_no_live_no_feishu_no_production_config_no_real_delivery
# WP6 implementation
approve_agent_run_supervisor_sachima_durable_runtime_integration_local_caller_owned_cross_process_claim_store_implementation_no_gateway_owned_lifecycle_no_worker_auto_start_no_live_no_feishu_no_production_config_no_real_delivery
```

---

### WP7 — Live / Gateway / Feishu delivery pilot

**Goal.** Reach the `GOAL.md` IM workbench: controlled external ingress, Gateway as the explicit delivery/ACK boundary, and a **limited, reversible** Feishu/IM real-delivery pilot of sanitized results.

**Scope.** Readiness **design only** first (ingress conformance, Gateway delivery-surface ownership, delivery-surface separation, ACK reconciliation, rollback/kill-switch, the `ROADMAP-WATCH-8788` exact-port concern), then — only after Rings A/B are production-hardened and **each delivery axis is separately approved** — a tightly bounded pilot. Each axis (ingress / Gateway / real delivery / ACK) is its own approval; none is bundled.

**Explicit non-approvals (until each axis is individually approved).** No public ingress; no Gateway mutation/restart/owned-Temporal lifecycle; no Feishu/IM real send; no production config writes; no default-on. Fake-send, loopback ingress, and HTTP 2xx do not approve real delivery.

**Files likely touched.** Gateway/adapter/ingress modules are **out of this mainline's current scope** and are named here only as design targets; concrete files are defined in the WP7 design packet, not here.

**Tests / evidence required.** Cross-repo Envelope v1 conformance (HMAC/schema/no-leak); delivery-surface separation tests; ACK reconciliation against real IM (not just 2xx); kill-switch/rollback drill; limited-pilot evidence outside the repo; Codex blocker re-review PASS per axis.

**Acceptance criteria.** Each delivery axis individually approved and proven reversible; sanitized-only delivery; raw material absent from durable history and user-visible evidence; kill-switch verified; dashboard updated.

**Suggested approval phrase (design only first).**
```text
approve_agent_run_supervisor_sachima_limited_live_gateway_feishu_delivery_pilot_readiness_design_docs_only_no_public_ingress_no_gateway_mutation_no_real_delivery_no_production_config
```

---

## 6. Recommended next PR (smallest safe step after Phase E-2)

**Recommendation: WP1a — Claude Code read-only role + capability-gate extension, injected fakes only, no real smoke.**

**Why this and not something larger or smaller.**
- It is the **single most meaningful gap**, not governance theater: today the engine matrix is Codex-only and **no Claude Code path has ever run from Sachima**. Adding a read-only Claude Code role is the first real second-engine increment and unblocks the whole "engineering-agent loop" (architect/reviewer in Claude, etc.).
- It is genuinely **small and safe**: a committed non-runnable role JSON plus a *minimal* "admit one read-only adapter" delta to the existing capability gate, with adversarial reject tests — exercised entirely with **injected fakes**. No real engine, no `acpx`, no network, no new lifecycle semantics.
- It matches the **proven rhythm** (Phase C wrapper with injected fakes → separately approved Phase D real smoke). WP1b (the one bounded real Claude Code smoke) is the immediately-following, separately approved step, not bundled here.

**Smallest-PR contents.** The new read-only Claude Code role config; the minimal capability-gate extension; admit/reject tests (read-only `claude` admitted; any write/execute/terminal/fetch capability and any non-`{codex,claude}` adapter rejected); no-leak + forbidden-surface tests; a `--self-test` smoke wiring with no real backend; full suite green; `compileall`; `git diff --check`; `codegraph status`; docs + manifest + dev log + dashboard sync; Codex primary blocker review PASS.

**Out of this PR.** Any real Claude Code execution (WP1b), multi-turn (WP2), cancellation (WP3), orchestration (WP4), write capability (WP5), durable runtime (WP6), and all of Ring C (WP7).

**Approval phrase to request for this PR:** the WP1a phrase in §WP1 above.

---

## 7. Risk register

| # | Risk | Where it bites | Mitigation (carried into every WP) |
|---|---|---|---|
| R1 | **Duplicate launches** — concurrent identical starts launch the engine twice | WP1b, WP2, WP4, WP6 | Atomic pre-launch claim/CAS (in-process now, cross-process at WP6); identical replay returns stored projection; concurrent-conflict tests + lock-removal mutation check; "exactly one supervisor session/turn" post-verify. |
| R2 | **Stale state / TOCTOU** — decisions made from a stale read; lease/epoch drift | WP2, WP3, WP6 | CAS on `state_version` **and** `lease_epoch`; lease-internal open-state recheck before launch; lifecycle guard re-reads inside the critical section; stale writers fail closed (`activity_session_stale_state` / `_toctou_conflict`). |
| R3 | **Raw output leakage** — prompt/output/tool output/exception text/PIDs entering durable state, logs, or evidence | every WP | Claim-check discipline: store only stable codes/refs/digests/counts; `session_binding` is an opaque hash, never a raw id/PID/path; `activity_supervisor_failed` collapses raw detail; no-leak + secret-shape scans gate every PR; evidence stays outside the repo. |
| R4 | **Prompt / tool over-permission** — a role gains more capability than intended | WP1, WP4, WP5 | Capability gate fails closed on any write/execute/terminal/fetch/mode-switch and any non-allowlisted adapter; role-file sha256 pinning; write capability only via the explicit WP5 flag inside a sandbox; adversarial reject tests required. |
| R5 | **Process / session leaks** — orphaned `acpx`/runner/child processes, temp/session dirs, dangling leases | WP1b, WP2, WP3, WP6 | "No leftover process" post-verify (generalized from Phase D); bounded session lifetime; graceful close + operator-gated abort; WP3 mandatory post-cancel cleanup assertion; lease released only after terminal write. |
| R6 | **Delivery side effects** — premature real send / Gateway mutation / Feishu call | WP7 (and any accidental import) | Gateway/Feishu/IM excluded by construction until WP7; forbidden-surface scan in every PR; delivery surfaces tracked separately; fake-send/2xx never count as real-delivery approval; per-axis approval + kill-switch at WP7. |
| R7 | **Branch / status drift** — dashboard or roadmap not updated; phase claims outrun evidence | every WP | `docs/roadmap/current-status.md` is the living index and must be synced per PR; phase markers + manifest scope booleans; "completion rule for agents"; if the dashboard is stale or contradicts the task, stop and report drift before changing files. |

---

## 8. Implementation sequencing table

| Order | Work package | Gate type | Depends on | Real exec? | Risk | Approval required (separate) |
|---|---|---|---|---|---|---|
| 1 | **WP1a** Claude Code read-only role + gate | Impl (fakes only) | Phase E-2 | No | Low | WP1a phrase |
| 2 | **WP1b** One bounded read-only Claude Code smoke | Real smoke | WP1a | Yes (1 run) | Med | WP1b phrase |
| 3 | **WP2** Multi-turn persistent session hardening | Impl + bounded real | WP1b | Yes (bounded) | Med-High | WP2 phrase |
| 4a | **WP3a** Cancellation request-state + interrupt API design | Design + impl (no fire) | WP2 | No | Med | WP3a phrase |
| 4b | **WP3b** Bounded cancellation execution | Real interrupt | WP3a | Yes (bounded) | High | WP3b phrase |
| 5a | **WP4 design** Controlled AI FLOW orchestration | Design (docs-only) | WP2, WP3 | No | Med | WP4 design phrase |
| 5b | **WP4 impl** Local read-only AI FLOW | Impl + bounded real | WP4 design | Yes (read-only) | High | WP4 impl phrase |
| 6a | **WP5 design** Write-capable roles + sandbox/rollback | Design (docs-only) | WP4 | No | High | WP5 design phrase |
| 6b | **WP5 impl** Sandboxed write roles | Impl + bounded real | WP5 design | Yes (sandboxed) | High | WP5 impl phrase |
| 7a | **WP6 design** Durable runtime + cross-process store | Design (docs-only) | WP4 (WP5 parallel) | No | High | WP6 design phrase |
| 7b | **WP6 impl** Local durable runtime + restart proof | Impl + restart smoke | WP6 design | Yes (local) | High | WP6 impl phrase |
| 8 | **WP7 design** Live/Gateway/Feishu pilot readiness | Design (docs-only) | WP5, WP6 hardened | No | Critical | WP7 design phrase |
| 9 | **WP7 pilot** Per-axis live delivery pilot | Real delivery (bounded) | WP7 design + per-axis approvals | Yes (live) | Critical | Per-axis phrases (not in this doc) |

**Ring mapping:** WP1–WP3 = Ring A; WP4–WP6 = Ring B; WP7 = Ring C. Design gates of a later WP may proceed in parallel with implementation of an earlier one, but **no WP's implementation/execution starts before its predecessor's evidence and its own approval exist.**

---

## 9. What NOT to do next

- **Do not** claim Claude Code is connected from Sachima. It is not. WP1a only adds a non-runnable role and a gate change exercised with fakes; the first real Claude Code run is WP1b and needs its own approval.
- **Do not** bundle WP1a + WP1b. Implementation-with-fakes and the first real smoke are separate gates, exactly as Phase C and Phase D were separated.
- **Do not** jump to live / Gateway / Feishu / real delivery, public ingress, or production config. Ring C is last and per-axis approved; fake-send, loopback ingress, and HTTP 2xx ACKs prove nothing about real delivery.
- **Do not** run cancellation execution, additional/unbounded persistent sessions, write-capable roles, controlled AI FLOW, Satine/Hermes-profile ACP, or any `npx`/network-fetch runner under WP1. Each is a later, separately named gate.
- **Do not** let the Gateway (or a Worker) own a Temporal/service/socket/subprocess lifecycle, even at WP6. Durable runtime stays caller-owned and local until a separate live gate.
- **Do not** widen the capability gate beyond "admit one read-only `claude` adapter." Any write/execute/terminal/fetch/mode-switch capability or non-allowlisted adapter must still fail closed, with adversarial reject tests.
- **Do not** pivot the mainline to agentic-ui Envelope v1 conformance; that remains an open **side tail**, not the next supervisor → Sachima step.
- **Do not** write raw prompts/outputs/tool output/exception text/PIDs/paths into durable state, logs, or in-repo evidence; keep all runtime evidence outside the repo.
- **Do not** treat merging *this* document as approval for anything. It is a planning/design gate only; every WP needs its own approval token and its own Codex primary blocker review.

---

### Handoff note

This plan has passed Codex CLI primary blocker review and Hermes arbitration as a docs-only planning artifact. It approves no implementation or execution. The recommended **first future implementation approval** is the **WP1a** approval token; WP1b real Claude Code smoke and all later work remain separately gated.
