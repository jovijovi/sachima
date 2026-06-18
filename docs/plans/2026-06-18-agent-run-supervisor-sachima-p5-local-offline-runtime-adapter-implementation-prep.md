# P5 local/offline runtime adapter implementation prep

Date: 2026-06-18
Status: **Docs-only implementation-prep / scope charter** — not source implementation. This packet defines the scope of the *next* P5 implementation PR; it adds no adapter code and starts no runtime.
Branch: `docs/p5-runtime-adapter-implementation-prep`
Base: `release/sachima` at `6c11a40d4de3e66981c3ff27905c1785b1709e0a` (the PR #147 merge commit; latest non-status-sync base per the machine status block)

> **For Hermes:** This is a **docs-only scope charter**. Do not write the runtime adapter, do not start or attach any runtime/Worker/service/socket/subprocess, do not run any AGENT/`acpx`/`npx`, and do not touch Gateway/Feishu/production config. It does **not** approve implementation, runtime start, Worker start, controlled AI FLOW execution, or any live/Gateway/Feishu/production/real-delivery axis. A separate implementation token (quoted below, **not granted here**) is required first.

## What this packet is

The P5 production durable runtime integration **design / readiness** packet merged in **PR #147** (merge commit `6c11a40d4de3e66981c3ff27905c1785b1709e0a`, mergedAt 2026-06-18T03:36:51Z). That packet already records the full contract: caller-owned runtime ownership, the `start`/`query`/`update`/`cancel`/`recover`/`close` control surface, durable records, the cross-process transactional claim store requirement, the no-throw boundary and failure taxonomy, the runtime-history no-leak rules (SCAN 1 + SCAN 2), the seven probes, the scoring rubric, kill criteria (K1–K8), and implementation gates (G0–G8).

This packet does **not** repeat that contract. It is a narrow **implementation-prep / scope charter** that fixes the shape, boundaries, and required tests of the **first** P5 implementation slice so the later implementation PR is small, caller-owned, fake-only, and reviewable. Read the merged PR #147 packet for the authoritative semantics:

- `docs/plans/2026-06-18-agent-run-supervisor-sachima-p5-production-durable-runtime-integration-design-readiness.md` (+ manifest, dev log)

## Status markers

```text
IMPLEMENTATION_PREP_ONLY
SCOPE_CHARTER_ONLY
NO_SOURCE_IMPLEMENTATION
RUNTIME_START_NOT_APPROVED
WORKER_START_NOT_APPROVED
FAKE_OR_INJECTED_RUNTIME_ONLY_FOR_NEXT_PR
CONTROLLED_AI_FLOW_EXECUTION_NOT_APPROVED
WRITE_ROLES_NOT_APPROVED
EXTERNAL_TEMPORAL_OR_WORKER_LIFECYCLE_SEPARATELY_UNAPPROVED
NO_LIVE
NO_GATEWAY
NO_FEISHU
NO_PRODUCTION_CONFIG
NO_REAL_DELIVERY
ARS_SACHIMA_P5_RUNTIME_ADAPTER_IMPLEMENTATION_PREP_ONLY
ARS_SACHIMA_P5_WP3B_ACTIVE_RUN_CANCELLATION_WATCH_PRESERVED
```

## Approval and boundary

User approved the exact prep-scope token (docs only; charter only; no implementation; no runtime/Worker start; no controlled AI FLOW execution; no live/Gateway/Feishu/production config/real delivery):

```text
approve_agent_run_supervisor_sachima_p5_local_offline_runtime_adapter_implementation_prep_docs_only_no_implementation_no_runtime_start_no_worker_start_no_controlled_ai_flow_execution_no_live_no_gateway_no_feishu_no_production_config_no_real_delivery
```

The **next** implementation token — the strongest allowed PR after this prep — is **not granted here**. It authorizes only a local/offline, caller-owned runtime adapter behind the existing WP4 executor Protocol seam, default-off, **fake/injected runtime only**, with **no real external runtime/Worker start**:

```text
approve_agent_run_supervisor_sachima_p5_local_offline_caller_owned_runtime_adapter_implementation_fake_or_injected_runtime_only_behind_executor_protocol_seam_default_off_no_real_runtime_start_no_worker_auto_start_no_gateway_owned_lifecycle_no_controlled_ai_flow_execution_no_live_no_gateway_no_feishu_no_production_config_no_real_delivery
```

Any **external Temporal service or Worker process lifecycle** remains separately unapproved and needs its own token (not granted, not implied by the implementation token above):

```text
approve_external_temporal_service_or_worker_lifecycle_for_sachima_p5_runtime
```

## Strongest allowed next PR (the scope this charter fixes)

After this prep merges, the next allowed PR is a **local/offline, caller-owned runtime adapter implementation** that:

- sits **behind the existing WP4 executor Protocol seam** (`StepExecutor` in `sachima_supervisor/ai_flow_executor.py`), invoked by the orchestrator exactly as the seam already is;
- is **default-off / injected**, and binds **only a deterministic fake/injected runtime** for tests — **no real external runtime, Worker, service, CLI, Docker container, socket, or subprocess is started or attached**;
- returns sanitized stable codes through a **no-throw** boundary and never raises across it;
- adds **no** new approval surface beyond the implementation token above.

It is one small adapter slice — not the durable backend, not a real runtime, not P6.

## Boundaries (carried into the next PR)

- no live / default-on behavior;
- no Gateway-owned lifecycle and no Gateway involvement or mutation;
- no Feishu/IM delivery, public ingress, production config, service restart/reload, platform adapter mutation, or real delivery;
- no controlled AI FLOW real execution (P6 stays blocked until P5 durable-runtime evidence passes);
- no write-capable roles (all roles stay read-only and bind only the existing capability-gated read-only role keys);
- no additional AGENT/`acpx`/`npx` real invocation;
- external Temporal/Worker lifecycle remains separately unapproved.

## Preserved P5 safety constraints (from PR #147)

The next PR must preserve, not weaken, the merged PR #147 constraints:

- **caller-owned control surface** — Sachima/FlowWeaver owns the runtime choice/lifecycle, control surface, and durable state; the supervisor library only calls the seam; the Gateway is never an owner/auto-starter;
- **cross-process transactional claim store required for durable claims** — the in-process lock-guarded CAS (`AiFlowRunStore` in `sachima_supervisor/ai_flow_store.py`) is single-process and insufficient for durable cross-process claims; the prep slice may model the abstraction with a fake, but must not present the in-process CAS as durable cross-process evidence (kill-criterion K2);
- **no-throw stable result/error taxonomy** — every adapter operation collapses backend exceptions to a stable `error_code`; no traceback/PID/backend detail crosses the boundary;
- **runtime-history no-leak** — SCAN 1 (sanitized JSON projection) **and** SCAN 2 (serialized event/history bytes); payloads cross the seam by claim-check ref/digest only;
- **probes** — duplicate-start, retry, timeout, cancellation, recovery, restart/replay, and query-snapshot consistency are the durable-runtime evidence bar;
- **WP3b active-run cancellation WATCH must not be overclaimed** — between-step cancel may be deterministic; active-run cancel stays best-effort/WATCH, held `cancel_ambiguous` with the `active_run_watch` marker, never promoted to `cancelled`, no artifact propagation, no relaunch.

## Allowed future code shape (high level only — not implemented here)

Named so the next PR is small and reviewable. These are **design labels**, not code added by this packet:

- a small **caller-owned adapter API / module** behind the `StepExecutor` Protocol seam (a `StepExecutor` binding plus a thin adapter entry), default-off and injected;
- sanitized **request/result dataclasses or equivalent** (aligned with the existing frozen `StepExecutionOutcome`: stable codes, refs, digests, counts — never raw bodies, never a business verdict from the executor);
- a **transactional claim-store abstraction** with a **deterministic local/offline fake implementation for tests only**, mirroring the `AiFlowRunStore` check-and-set / validate-on-read contract while modeling the cross-process claim semantics PR #147 requires;
- **query / recovery / cancel / close** wrappers that return stable codes and **never throw across the boundary**, reusing the WP3b-aligned cancellation channel (`interrupted` / `cleanup_verified` / `ambiguous`) rather than inventing new semantics.

## Tests the future implementation PR must include

The implementation PR is not complete without deterministic, local/offline, fake-only tests for at least:

- **exact approval token** — wrong/missing implementation token fails closed;
- **duplicate start** — two identical starts converge to one run (`idempotent_replay`);
- **idempotent replay** — a compatible repeat returns the stored projection with no second executor call;
- **conflict fail-closed** — an incompatible repeat / conflicting starter fails closed (no double-launch);
- **unsafe material rejection** — platform/private/secret/raw/card/media material is rejected (`runtime_unsafe_material`);
- **resident dirty state rejection / sanitization** — a hostile resident record can never be projected (validate-on-read);
- **lease / epoch / state_version TOCTOU** — drift between validation and durable apply fails closed before mutation;
- **active-run cancellation WATCH** — unconfirmed active-run interruption held `cancel_ambiguous` + WATCH, never `cancelled`;
- **no-leak scans** — SCAN 1 (JSON projection) **and** SCAN 2 (serialized event/history bytes);
- **forbidden-surface static guard** — the adapter imports/starts no real runtime/Worker/subprocess/socket/acpx/npx surface.

## Governance posture (reduction rule)

Safety governance stays **strong**: the next PR carries its own scope manifest, guard tests, the two no-leak scans, the forbidden-surface scan, and an independent blocker review.

Status governance stays **light**: no standalone PR is opened merely to record merge status; full non-approval paragraphs are not duplicated across every doc — they live authoritatively in PR #147 and `GOAL.md` and are referenced, not copied; stale status fixes (e.g. the PR #147 "pre-merge" wording) fold into a same-scope PR (this one) rather than spawning a status-only PR.

## Explicit non-approvals

This charter does **not** approve implementation, runtime/Worker start or attach, cross-process claim-store as a real service, controlled AI FLOW execution (P6), write-capable roles, additional AGENT/`acpx`/`npx`, real local exec, persistent-session execution, additional/unbounded cancellation execution, Gateway-owned/auto-started lifecycle, external Temporal/Worker startup, Gateway involvement/mutation, platform adapter mutation, real external ingress, public webhook exposure, Feishu/IM delivery, real delivery, production config writes, service restart/reload, or live/default-on behavior. The authoritative non-approval list is in PR #147's packet and `GOAL.md`; it is referenced here, not re-expanded.

## Verification gates (docs-only PR)

This PR is docs/status only; no runtime tests run.

- [ ] Status markers present; scope is prep/charter only, not implementation.
- [ ] Three tokens quoted: prep token (approved), next implementation token (not granted, fake/injected runtime only), external Temporal/Worker token (not granted).
- [ ] Strongest-next-PR scope, boundaries, preserved PR #147 safety constraints, allowed code shape, and required tests all present.
- [ ] Manifest YAML-parseable; false booleans for implementation/runtime start/Worker start/controlled AI FLOW/Gateway/Feishu/live/production config/real delivery.
- [ ] Changed-file allowlist is docs/status only (this packet + manifest + dev log + the narrow current-status update + minimal PR #147 status patches).
- [ ] Stale PR #147 status scan: no remaining pre-merge PR #147 status markers or null merge fields for PR #147 in human-authored docs.
- [ ] Forbidden live/Gateway/Worker/Feishu/runtime-start surface scan on changed files (non-approval prose allowed); secret/no-leak scan; Codex blocker-only review on the final diff.

Hermes runs these gates and the Codex review; the author does not commit, push, merge, run tests, attach a runtime, or touch runtime/Gateway/Feishu/production config.

## Closure rule

This charter only makes the P5 **local/offline, caller-owned, fake-runtime adapter implementation** eligible to request with its own exact token. It authorizes no source implementation, no runtime/Worker start, no durable-backend attach, no controlled AI FLOW execution (P6), no external Temporal/Worker lifecycle, and no live/Gateway/Feishu/production/real-delivery axis. P6 stays blocked until the P5 durable-runtime probe evidence passes.
