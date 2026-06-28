All five prior P1 points verified against the actual repo files (not just the inline excerpts). The `start` mapping fix is at point-of-use, the `批准实施` scoping and approval-phrase/non-goals coupling are in place, FR2 carries `detach`/`terminalize`, and the reference-index/phase-ledger/tail-register all carry "docs-only candidate" framing.

# Claude Teach-back — P6 Runtime Lifecycle / Controlled Attach Plan

## Verdict
PASS — all five prior P1 hardening points are resolved at point-of-use with no accidental approval of any forbidden axis; this remains a docs-only governance gate that starts no implementation, runtime, or real execution.

## Architecture teach-back
- Future `P6RuntimeAttachSession` is a **thin controlled-attach shell** over existing `P6ControlledAiFlowSession` + `P5TemporalControlSurface`/`P5TemporalStepExecutor` — a lifecycle wrapper, never a runtime owner (tech-solution §0).
- Caller owns the runtime/control surface; `attach` validates a caller-supplied client/capability shape and binds it to a P6 session **without** spawning Worker/service/subprocess/socket/Docker/Gateway lifecycle; unsafe material fails closed before any workflow/activity/agent call (PRD FR1; tech-solution §3).
- Lifecycle state machine `attach -> start -> query/update/cancel/recover* -> close/terminalize -> detach`, each op returning stable codes + safe projections only (PRD FR2).
- Every mutating op binds run/workflow/step ids + idempotency_key/fingerprint + lease/epoch/state_version + role digest + sanitized backend ref; identical replay returns the stored projection, divergent/stale fails closed (PRD FR3; tech-solution §6).
- `recover`/`query` are reattach/read-only; ambiguous recovery returns `recover_ambiguous`/WATCH and never relaunches (PRD FR4; tech-solution §6).
- Health/drain/kill-switch/rollback degrade toward a local-offline/fake adapter and detach **without** touching Gateway or terminating workflows (PRD FR5; tech-solution §5).
- No-leak across four surfaces (P6 snapshots, WP4 store, P5 projections/history bytes, user-visible docs) plus a forbidden-marker canary (PRD FR6; tech-solution §7).

## P0/P1 blockers
None. Re-verification of the five prior P1 points:
1. **start excludes real runner** — RESOLVED at point of use: tech-solution §4 `start` row Hard rule bolds "first-slice executor binding is deterministic/injected-fake/local-offline only and must NOT bind the reusable P6-B real-agent runner without a separate real-execution approval"; reinforced by §9 RED step 1 and the user-review-packet "Recommended later implementation scope."
2. **`批准实施` scoping** — RESOLVED: PRD "Scope of this artifact" states it "authorizes **only** ... this docs-only ... governance gate" and "explicitly does **not** authorize source implementation, runtime start, Worker start, ...".
3. **approval phrase read with non-goals** — RESOLVED: PRD "Later implementation approval phrase" appends "Read that phrase together with the non-goals list above ...", keeping service restart/ingress/traffic/adapter mutation/broader FLOW forbidden and any real-execution approval separate and individually named.
4. **detach/terminalize in state machine** — RESOLVED: PRD FR2 now contains `close/terminalize -> detach`; tech-solution §4 adds an explicit `detach` row ("must not stop Worker/service/Gateway") plus close-with-detach-marker.
5. **reference-index/phase-ledger framing** — RESOLVED: reference-index lines 57–58 label it "(docs-only candidate)"; phase-ledger line 45 "Candidate docs-only governance ... No implementation/runtime/live approval"; tail-register line 21 "Candidate docs-only gate ... no implementation/execution/live approval yet"; boundary-register scoped-grant note reaffirms docs-only.

## Boundary / non-approval audit
No accidental approval detected on any forbidden axis.
- Manifest `scope:` sets `source_implementation`/`runtime_start`/`worker_start`/`gateway_involvement`/`feishu_or_im_delivery`/`production_config_write`/`service_restart`/`real_delivery`/`additional_real_agent_execution`/`write_roles` all **false**, `docs_only: true`; `strongest_allowed_outcome` is explicitly docs-only.
- PRD Non-goals/non-approvals align with current-status "Explicit non-approvals" and boundary-register; the PR #181 smoke is held as a one-shot prerequisite, not a general license (PRD FR8).
- WP3b active-run cancellation stays WATCH, not redefined as success (PRD FR7; tech-solution §4 cancel row; tail-register line 21).
- `detach`/kill-switch are explicitly forbidden from stopping Worker/service/Gateway or terminating workflows (tech-solution §4/§5); rollback may not restart Gateway or mutate production config.

## Required fixes before PR
None required. One optional, non-blocking polish: tech-solution §4's operation table maps `close` and `detach` but folds `terminalize` into the PRD's `close/terminalize`; a one-line `terminalize` row (terminal close that still performs no delivery/disconnect) would make §4 fully mirror FR2. Not a blocker — FR2 already names terminalize and the detach row is present.

## Implementation handoff sanity
The future approval phrase (`approve_agent_run_supervisor_sachima_p6_runtime_lifecycle_controlled_attach_implementation_default_off_caller_owned_attach_only_no_runtime_or_worker_start_no_additional_real_agent_execution_no_write_roles_no_live_no_gateway_no_feishu_no_production_config_no_real_delivery`) is sufficiently narrow: default-off, caller-owned attach-only, self-excluding runtime/Worker start, additional real agent execution, write roles, live, Gateway, Feishu, production config, and real delivery — and the PRD binds it to the non-goals while keeping any real-execution approval separate and individually named (exact runner/backend/scope/run-count/time-budget/evidence-root). A future implementation under it must prove: fail-closed disabled/mismatched attach with zero backend calls and **no real-runner binding**; sanitized attach/health projections; idempotent identical-replay plus fail-closed divergent/stale lease/epoch/state_version; `recover`/`query` read-only with no relaunch; WP3b WATCH propagation; four-surface no-leak canary; and forbidden-surface scans — all on deterministic/injected-fake/local-offline executors only.
