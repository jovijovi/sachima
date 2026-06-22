# Dev Log — agent-run-supervisor × Sachima Phase E — Persistent Sessions & Cancellation Design

Date: 2026-06-13
Branch: `docs/phase-e-persistent-sessions-cancellation-design`
PR: #123 — https://github.com/jovijovi/sachima/pull/123 (merged; merge commit `9e435eb443de67a923c43787f5ef7cb8ae8ad981`)
Base: `release/sachima` @ `10102f595983727e7f569f58e9beadf9554fdfae` (Phase D real smoke status closure)

## Approval Phrase and Boundary

User approval received in chat (verbatim):

```text
批准准备 Phase E persistent sessions / cancellation docs-only design gate，仍遵循 AGENT 分工，不批准 live/Gateway/Feishu/生产/真实投递。
```

Boundary recorded:

- **Approved:** preparing the Phase E persistent sessions / cancellation **docs-only design gate**, following the established AGENT split.
- **Not approved:** live behavior, Gateway involvement, Feishu/IM involvement, production config/surfaces, real delivery — and, per the standing roadmap non-approvals, implementation of any kind, persistent session execution, cancellation execution, additional real AGENT/acpx execution, write-capable roles, Satine/Hermes-profile ACP, and controlled AI FLOW execution.

## AGENT Split

```text
Hermes      = PM / controller / verifier / repo operator / evidence arbiter
              (runs all gates, commits, opens the PR, arbitrates evidence)
Claude Code = architect + documentation engineer for this docs-only design gate
              (authored the 4 docs/status files only)
Codex CLI   = primary blocker reviewer after the draft (fresh context, blocker-only)
```

## Execution Discipline Record

The authoring pass for this gate:

- changed **docs/status files only** (the 4 allowlisted paths below);
- made **no** source code, test, role JSON, fixture, config, runtime, or service change;
- ran **no** AGENT, no `acpx`, no `npx`, no Codex/Claude through the supervisor, no supervisor/runtime invocation, no Gateway, no Feishu/IM, no public ingress, no production config write, no service restart/reload, no platform adapter mutation, no real delivery, and no persistent-session or cancellation execution;
- read `sachima_supervisor/local_offline.py`, `activity_controlled_exec.py`, `activity_preflight.py`, and `supervisor_library.py` **for factual reference only**; none were edited;
- did not commit, push, open a PR, or merge (Hermes owns repo operations).

## Roadmap Preflight (per AGENTS.md)

Read before writing: `AGENTS.md` (preflight + phase rules), `GOAL.md`, `docs/roadmap/current-status.md`, the canonical roadmap pointer, the PR #102 durable-runtime design packet + manifest + dev log, the PR #107 preflight plan, the PR #114 Phase C plan, the Phase D smoke manifest and dev log.

State of the world at preflight:

- Current position: Phase C `exec_controlled` one-shot wrapper merged (PR #114); Phase D readiness (PR #117) and smoke prerequisites (PR #119) merged; one separately approved host-local read-only Codex one-shot smoke PASSED through pinned local acpx 0.10.0; evidence outside the repo.
- Next allowed request per current-status: a **new docs-only design gate** for the next supervisor → Sachima capability — exactly this task.
- Explicit non-approvals (unchanged and preserved): persistent_session_execution, cancellation_execution, additional real smoke/AGENT/acpx, write-capable roles, Satine/Hermes-profile ACP, controlled AI FLOW, Gateway/Feishu/live/public ingress, production config, real delivery.
- Open tails: `ROADMAP-WATCH-8788`, `ROADMAP-WATCH-STATUS-DASHBOARD`, `ROADMAP-NEXT-P4-ENV-V1-CONFORMANCE` (side tail), `ROADMAP-NEXT-ARS-CONTROLLED-AI-FLOW`. None blocks a docs-only design gate.
- Conclusion: the requested task is allowed by current-status as the recommended docs-only next step; no drift detected.

## What the Design Packet Decides (summary)

- Adopts the PR #102 deferred labels (`session_open`, `session_turn`, `session_closed`, `cancel_requested`, `cancelled`, `rolled_back`) and gives them full **design-only** semantics; execution stays unapproved on every axis.
- Ownership inherited unchanged: Sachima/FlowWeaver caller owns durable product/session state and business decisions; `agent-run-supervisor` owns local session/run internals and redacted evidence only after approved invocation; Gateway and Feishu excluded.
- Persistent session model: `SessionRecord` / `TurnRecord` design labels; lifecycle states; lease/epoch/`session_binding`; command semantics for create/send/query/close/abort/list; local-only, default-off, caller-owned, role-bound, pinned-acpx/pinned-supervisor-library prerequisites; **lease-internal open-state recheck** before any launch; **lifecycle-guard re-read** for close/abort/cancel; explicit stable lock ordering (store lock → lifecycle guard → future supervisor handle; never a supervisor call under the store lock); list/query are durable projections that must not contact live sessions (the seam-level `session_status` bounded local call stays a later explicit allowance).
- Cancellation model: request vs execution distinction; `CancellationRequestRecord` with operator gate, lease binding, idempotency, terminal/ambiguous states; **cancellation execution not approved**; eight future requirements (supervisor interrupt support, external process/session identity binding, cleanup guarantees, no double-close, partial-artifact handling, redacted evidence, race regression tests, separate approval) recorded before it can ever be implemented.
- Concurrency rules: idempotency unit (key, fingerprint, lease epoch); stale-state and TOCTOU CAS rules; fail-closed on ambiguous prior run/session state with **no duplicate launch to resolve ambiguity**; required race regression test list for any future implementation.
- No-leak rules: durable state/logs may hold stable codes, role key, sanitized refs/digests/counts/leases/epochs/attempt indices/opaque session binding only; never raw prompt/context/model output/tool output/acpx stdout/card JSON/media paths/platform IDs/secrets/raw exceptions/arbitrary absolute paths/PIDs.
- Failure taxonomy extension: `activity_session_disabled`, `activity_session_approval_mismatch`, `activity_session_already_open`, `activity_session_not_open`, `activity_session_binding_mismatch`, `activity_session_lease_lost`, `activity_session_stale_state`, `activity_session_toctou_conflict`, `activity_session_turn_ambiguous`, `activity_cancel_not_approved`, `activity_cancel_ambiguous`, `activity_lifecycle_conflict`, `activity_budget_exceeded`, `activity_supervisor_failed` (inherited codes remain in force).
- Future implementation gates: **Option A recommended** — local/offline persistent-session lifecycle preflight / state-machine slice with injected fakes, no real session launch, no cancellation execution; Option B (bounded local session) and any cancellation-execution slice only later, each under its own approval, all still no live/Gateway/Feishu/production/real delivery.

## Files Changed

```text
docs/plans/2026-06-13-agent-run-supervisor-sachima-phase-e-persistent-sessions-cancellation-design.md            (new — design packet)
docs/plans/2026-06-13-agent-run-supervisor-sachima-phase-e-persistent-sessions-cancellation-design-manifest.yaml (new — manifest)
docs/dev_log/2026-06-13-agent-run-supervisor-sachima-phase-e-persistent-sessions-cancellation-design.md          (new — this dev log)
docs/roadmap/current-status.md                                                                                  (updated — latest fields, current_position, phase map row, references, tail, next allowed request, drift guard)
```

No code, tests, fixtures, roles, configs, or `.hermes` files were created or modified.

## Expected Review / Verification Gates (run by Hermes)

```text
docs marker gate (11 status markers, incl. NO_FEISHU and NO_PRODUCTION_CONFIG)
manifest YAML parse + required keys (status: design_merged; docs_only: true; all execution/live/production/delivery booleans false)
post-merge status sync check against docs/roadmap/current-status.md (PR #123 merged; merge commit recorded)
changed-file allowlist (exactly the 4 paths above)
no source diff (nothing under sachima_supervisor/, tests/, roles, configs, runtime/service files)
secret-shaped / no-leak scan
forbidden-surface scan (no runnable Gateway/Feishu/acpx/npx/service-restart steps introduced)
optional, Hermes' choice: pytest -q tests/sachima_supervisor (unchanged suite) and python3 -m compileall -q sachima_supervisor tests/sachima_supervisor
CodeGraph status (or N/A for docs-only worktree per AGENTS.md)
Codex CLI primary blocker review from a fresh context (VERDICT: PASS / BLOCKERS: None required before PR completion)
```

Author-run safe checks during drafting (docs-only): manifest YAML parse via Python `yaml.safe_load`, `git diff --check`, and a marker/changed-file self-check. No runtime, supervisor, acpx, Gateway, or Feishu surface was touched.

## Next Decision After This Gate

After PR #123 merged, the next safe request is still the **Option A** implementation gate only:

```text
approve_agent_run_supervisor_sachima_phase_e_persistent_session_lifecycle_preflight_state_machine_local_offline_implementation_no_real_session_launch_no_cancellation_execution_no_real_agent_execution_no_live_no_gateway_no_feishu_no_production_config_no_real_delivery
```

Persistent session execution, cancellation execution, additional real AGENT/acpx execution, write-capable roles, Satine/Hermes-profile ACP, controlled AI FLOW execution, live/Gateway/Feishu/public ingress, production config writes, service restarts, platform adapter mutation, and real delivery all remain blocked behind separate, later, separately named approvals. Do not pivot to agentic-ui by default; that conformance work remains an open side tail.
