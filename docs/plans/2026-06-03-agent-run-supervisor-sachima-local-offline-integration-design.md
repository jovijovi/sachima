# agent-run-supervisor × Sachima Local/Offline Integration Design Packet

> **For Hermes:** This is a design packet only. Do not implement anything from this document unless Dog Brother later gives the exact, separately named implementation approval quoted in the "Future Implementation Phases" section. Use TDD, `subagent-driven-development`, `phase-gate-drift-control`, and fresh blocker review for any later implementation.

**Goal:** Define how a local Sachima/FlowWeaver/Hermes controller could use `agent-run-supervisor` as a local supervisor *library* to compile and observe a supervised AGENT run/session, returning redacted evidence and a caller-owned view model — strictly local/offline, with no live behavior, no Gateway involvement, and no real delivery.

**Architecture (design intent only):** A caller owned by Sachima/FlowWeaver/Hermes (a transaction/Activity wrapper or controller seam — **not** the Gateway) assembles a sanitized invocation, calls the supervisor library to run/observe an `acpx`/ACP AGENT locally, and receives supervisor status, artifact refs, and a normalized result summary. The caller alone interprets the business verdict and builds an offline progress/result view model. Nothing is delivered to any IM/Feishu surface.

**Tech basis:** `agent-run-supervisor` (independent local Python library + dev CLI) `src/agent_run_supervisor/caller.py` (I1 generic caller boundary: `CallerInvocationSpec`, `CallerResult`, `invoke_caller`) and `src/agent_run_supervisor/hermes_caller/` (L2 local/offline caller with offline Feishu view-model/payload dicts); Sachima `GOAL.md`, gap analysis, phase plan, and prior PE-1D / Phase B / PE-2A / P4 evidence already on record. Docs / changed-file / no-leak gates only.

---

## Status Markers

```text
DESIGN_ONLY
IMPLEMENTATION_NOT_APPROVED
LIVE_NOT_APPROVED
GATEWAY_NOT_APPROVED
REAL_DELIVERY_NOT_APPROVED
```

Scoped equivalents for grep/dashboard use:

```text
ARS_SACHIMA_LOCAL_OFFLINE_DESIGN_ONLY
ARS_SACHIMA_LOCAL_OFFLINE_IMPLEMENTATION_NOT_APPROVED
ARS_SACHIMA_LOCAL_OFFLINE_LIVE_NOT_APPROVED
ARS_SACHIMA_LOCAL_OFFLINE_GATEWAY_NOT_APPROVED
ARS_SACHIMA_LOCAL_OFFLINE_REAL_DELIVERY_NOT_APPROVED
```

Strongest allowed outcome of this PR:

```text
agent_run_supervisor_sachima_local_offline_integration_design_ready_for_separate_local_offline_implementation_request
```

That outcome means the next, separately named local/offline implementation request *may be asked for*. It does **not** mean implementation, live/default-on behavior, Gateway involvement, real external ingress, real delivery, production config writes, or controlled AI FLOW execution are approved.

## Approval and Boundary

User-facing approval text received in the chat:

```text
approve_agent_run_supervisor_sachima_local_offline_integration_design_no_live_no_gateway_no_real_delivery
```

This token approves **local/offline integration design only**: a docs-only design packet for using `agent-run-supervisor` as a local supervisor library under a Sachima/FlowWeaver caller. It does not approve runtime code implementation, live/default-on behavior, Gateway restart/reload/replace, production config writes, real external ingress, real IM/Feishu delivery, public webhook exposure, automatic replies, worker auto-routing, platform adapter mutation, or Gateway-owned lifecycle.

The design is and stays **caller-owned by a Sachima/FlowWeaver/Hermes controller**. This packet deliberately does **not** name the Gateway as the concrete caller. The Gateway may become a future presentation/ingress surface only after a separate, explicitly named approval.

## Goal Trace

```text
Goal: Sachima becomes Dog Brother's safe, durable, observable, recoverable IM AI workbench that can run long AI FLOW
      tasks (planning, coding, testing, PR creation, CI wait, merge coordination, reports) and deliver sanitized results.
Gap:  The controlled AI FLOW capability (gap-analysis §4 "Production agent/tool execution"; phase plan "Phase F —
      Controlled AI FLOW execution") needs a supervised, observable, evidence-producing local AGENT run/session seam
      that a FlowWeaver caller can drive. Current evidence has local controlled Activity boundaries and stub
      orchestration, but no caller-owned local supervisor seam that compiles a role into an acpx/ACP invocation,
      parses observed events, classifies status, and emits redacted artifacts/audit evidence.
Phase: Docs-only local/offline integration design packet, positioned after P4 Sachima-side conformance and before
      P5 production durable runtime and P6 controlled AI FLOW execution.
Task: Define the caller boundary mapping (Sachima/FlowWeaver controller -> agent-run-supervisor I1 generic caller and
      L2 local/offline caller), the input and output contracts, mode mapping, the FlowWeaver integration seam,
      no-leak boundaries, explicit non-approvals, acceptance checklist, and the next approval texts.
Test: Docs gate, manifest parse/marker gate, changed-file allowlist, no-secret/no-leak scan, and two independent
      reviews (consistency / phase-gate; security / low-intrusion), plus an independent Codex primary review.
Evidence: This design packet, its manifest, and dev log; the current-status update; the cross-repo agent-run-supervisor
      I1/L2 authority facts; and the Sachima PE-1D / Phase B / PE-2A / P4 evidence already on record.
Decision: May request a separately named local/offline implementation approval only. Live, Gateway-owned, real-delivery,
      and controlled-AI-FLOW behavior remain blocked.
```

## Level Selection

**Level 3 — High Risk.**

Conservative reason: although this PR is docs-only and the integration is local/offline, the subject matter is production-adjacent. It touches the agent-execution boundary, the Gateway boundary, and the live-delivery boundary at the design level. Ambiguity here would become live implementation risk later, so the packet is held to the same scope/non-approval discipline as a production-adjacent design packet rather than a standard low-risk docs change.

## Evidence Inputs

| Evidence | Current state | Design impact |
|---|---|---|
| `GOAL.md` | Requires safety before live capability, low intrusion, explicit per-axis approvals, claim-check discipline, and delivery separation. | The supervisor integration must stay caller-owned, local/offline, default-off-by-design, and approval-gated; the Gateway must not silently own lifecycle. |
| `docs/sachima-final-goal-gap-analysis.md` §4 / Phase F | Local controlled Activity evidence exists; production agent/tool execution from Sachima is blocked; controlled AI FLOW needs claim-check inputs, no-throw Activities, approvals, sanitized progress. | A local supervised AGENT run/session seam with redacted evidence is the missing caller-owned building block this packet designs. |
| `docs/roadmap/current-status.md` | P4 Sachima-side local conformance implemented; P5/P6 pending; broad non-approvals intact. | This packet inserts a docs-only local/offline supervisor integration design after P4 and before P5/P6; it must not imply P5/P6 work started. |
| Sachima PE-2 design packet (`docs/plans/2026-05-12-flowweaver-pe2-design-packet.md`) | Established the caller-supplied control surface pattern and the "design packet ≠ implementation" boundary. | Reused: the supervisor is invoked through a caller-supplied seam; this packet does not authorize runtime/lifecycle. |
| agent-run-supervisor authority — I1 generic caller | `src/agent_run_supervisor/caller.py` with `CallerInvocationSpec`, `CallerResult`, `invoke_caller`; `CallerResult.business_verdict` remains `None`/null. | This is the generic seam the Sachima caller targets. The caller, not the supervisor, sets business intent and verdict. |
| agent-run-supervisor authority — L2 local/offline Hermes caller | `src/agent_run_supervisor/hermes_caller/` with offline Feishu view-model/payload **dicts**; no Feishu SDK/API, no IM delivery, no public ingress, no Gateway/Sachima behavior, no automatic replies, no live/default-on. | Offline view-model dicts are a *reference shape* for caller-owned rendering only. Real Feishu/IM delivery stays out of scope. |
| agent-run-supervisor ownership split | Library owns `AgentRoleSpec`, `acpx`/ACP invocation compilation, local run/session lifecycle, observed stdout/event parsing, status classification, redacted local artifacts/audit evidence. Callers own product/business intent, verdict interpretation, rendering/progress/delivery/platform integration. | The contracts below preserve this split exactly. |

## Core Design Decision

```text
The concrete caller is a local Sachima/FlowWeaver/Hermes controller or Activity wrapper.
The concrete caller is NOT the Gateway.
agent-run-supervisor stays a local library / evidence layer; it is not Sachima, not a Gateway plugin, not an IM adapter, not a daemon.
```

Rationale:

1. The supervisor library already owns execution mechanics (role spec, `acpx`/ACP compilation, run/session lifecycle, observed-event parsing, status classification, redacted evidence). The Sachima side already owns product intent, verdict interpretation, and rendering. The integration only needs a thin caller seam between them; no new ownership is created.
2. Keeping the caller as a FlowWeaver controller/Activity wrapper preserves the GOAL.md low-intrusion principle: the Gateway does not gain a hidden execution or lifecycle dependency from message handling.
3. The generic I1 boundary (`invoke_caller` returning a `CallerResult` whose `business_verdict` is always `None`) enforces the split mechanically: the supervisor never decides the business outcome.
4. Naming the Gateway as the caller now would couple agent execution to the live presentation/ingress surface before that surface is separately threat-modeled and approved. The Gateway is therefore explicitly deferred.

## Architecture (Text Diagram)

```text
[ Sachima request / operator intention ]               OWNED BY Sachima (product + business intent)
            │  sanitized turn facts + claim-check refs + role choice
            ▼
[ FlowWeaver transaction / Activity / controller seam ]   THE CALLER — Sachima/FlowWeaver/Hermes (NOT the Gateway)
            │  builds CallerInvocationSpec
            │  { role, assembled prompt/context (from refs), cwd/allowed roots,
            │    exec|session mode, run/session artifact dirs, correlation ids }
            ▼
[ agent_run_supervisor.caller.invoke_caller  — I1 generic boundary ]   LOCAL LIBRARY
            │  compiles AgentRoleSpec -> acpx/ACP invocation
            ▼
[ acpx / ACP AGENT — local one-shot exec OR persistent session ]   observed only
            │  observed stdout / events
            ▼
[ supervisor: parse events -> classify status -> write REDACTED local artifacts/audit evidence ]
            │  returns CallerResult { status, artifact_refs, normalized events/result summary,
            │                         business_verdict = None }
            ▼
[ caller-owned interpretation ]   OWNED BY Sachima/FlowWeaver
            │  business verdict (caller decides) + progress/result VIEW MODEL
            │  (optional) L2 offline Feishu view-model/payload DICTS only — no SDK, no API, no send
            ▼
[ NO REAL DELIVERY ]   offline view models + local evidence only
            ✗ no IM/Feishu send   ✗ no public ingress   ✗ no Gateway lifecycle   ✗ no automatic replies
```

## Caller-Owned Input Contract

The caller assembles a `CallerInvocationSpec` (the I1 generic shape). All product/business intent lives here, on the caller side:

| Field (intent) | Owner | Notes |
|---|---|---|
| Role selection | Caller | Caller chooses which role/`AgentRoleSpec` to run for this intention. |
| `AgentRoleSpec` mapping | Library defines, caller selects | The library owns the role→`acpx`/ACP invocation template (command profile, allowed tools, model-profile labels). The caller only references a role by id; it does not hand-build invocation command lines. |
| Prompt / context assembly | Caller | Caller composes the prompt and context from **claim-check refs and sanitized text**, not from raw platform payloads. |
| `cwd` / allowed roots | Caller | Working directory and the explicit allowed filesystem roots for the run. |
| Exec / session mode | Caller | One-shot `exec` vs persistent `session` (see Mode Mapping). |
| Run / session artifact dirs | Caller | Local directories where the supervisor writes redacted artifacts and audit evidence. |
| Correlation ids | Caller | Caller-owned correlation labels (e.g. transaction label, turn-label digest). |

**Forbidden in the generic supervisor API:** platform-private IDs (chat/user/message IDs), raw platform payloads, card JSON, media bytes/paths, credentials/tokens, raw signatures. Platform-private identity stays on the caller side and is mapped to caller-owned correlation labels before invocation. The generic supervisor boundary must remain platform-agnostic.

## Output Contract

`invoke_caller` returns a `CallerResult` (the I1 generic shape):

| Field | Owner | Notes |
|---|---|---|
| Supervisor status | Library | Classified terminal/transient status from observed events (e.g. completed / failed / cancelled / timed-out / needs-input). Status taxonomy is library-owned and stable. |
| Artifact refs | Library | References to **redacted** local artifacts / audit evidence. Refs and labels only — never raw bytes. |
| Normalized events / result summary | Library | Sanitized, structured summary of observed run/session events. |
| `business_verdict` | Caller (stays `None` from library) | The library always returns `business_verdict = None`/null. The caller interprets the supervisor status + summary into a business verdict. |
| Progress / result view model | Caller | Built by the caller from status + refs + summary. May follow the L2 offline Feishu view-model/payload **dict** shapes for offline rendering only. |

**No raw outputs in durable state or cards:** raw `acpx` stdout, raw tool output, raw model text, and raw exceptions/tracebacks must never enter durable FlowWeaver/Sachima state or any user-visible card. Durable state and cards carry sanitized refs, counts, digests, statuses, stable error codes, and caller-built summaries only.

## Mode Mapping

| Mode | Behavior (design intent) | Status |
|---|---|---|
| One-shot `exec` | Single invocation: compile → run → classify terminal status → write redacted artifacts → return `CallerResult`. | In scope for later local/offline implementation. |
| Persistent `session` | Open a supervised session, drive one or more turns, query status, then close. Session handle/lifecycle stays caller-driven through the library API. | In scope for later local/offline implementation. |
| Dry-run / config-preview | Compile the `AgentRoleSpec` into the planned `acpx`/ACP invocation and surface the planned command + role spec **without executing**. Safest possible local probe. | Preferred first concrete step for a later local/offline implementation; still needs its own approval. |
| Status / close / cancel | Caller can query session status, close a session, and request cancel. | Status/close in scope for later implementation; **cancellation and rollback semantics** (mid-run interruption, partial-artifact handling, idempotent re-entry) are **future implementation concerns to be designed and implemented later**, not approved here. |

## FlowWeaver Integration Plan

The integration is designed as a **local/offline Activity or controller seam**, not a runtime owner:

1. **Claim-check refs at the boundary.** The Activity/seam receives claim-check refs and sanitized labels; raw user/platform material never enters Activity arguments or durable history.
2. **No-throw wrappers.** The Activity/seam must catch every supervisor error and map it to a stable status + error code. Raw exception text and tracebacks never propagate into durable FlowWeaver/Sachima history, logs, or cards.
3. **Query / update / cancel semantics — later.** Durable query/update/cancel and recovery semantics are explicitly *not* designed-to-completion here and *not* approved here, because that requires the P5 production durable runtime ownership decision (which keeps the runtime caller-supplied, never Gateway-owned).
4. **Evidence-only local probe.** The only concrete step a later, separately approved local/offline implementation should take first is a default-off, local, evidence-producing probe — e.g. dry-run/config-preview compilation plus offline view-model construction — emitting sanitized evidence under local `outputs/`. Even that probe requires the separate implementation approval named below.

## Safety / No-Leak Boundaries

The following must **never** enter durable FlowWeaver/Sachima state or user-visible cards:

```text
raw prompts
platform ids (chat/user/message/private ids)
card JSON
media bytes or media paths
tool output
tokens / credentials / secrets / raw signatures
raw acpx stdout
raw exceptions / tracebacks
```

Additional invariants:

- `CallerResult.business_verdict` stays `None`/null from the library; the caller owns verdict interpretation.
- The generic supervisor API stays platform-agnostic; platform-private identity is mapped to caller-owned correlation labels before invocation.
- Delivery surfaces stay separated *in the offline view model only*; building a view model is not delivery, and no send occurs.

## Explicit Non-Approvals

This design packet does **not** approve:

```text
real_external_sachima_ingress
real_external_delivery
production_delivery_control
production_agent_tool_execution_expansion
production_config_write
gateway_restart_or_reload
platform_adapter_mutation
gateway_owned_temporal_lifecycle
real_send_api_or_external_im_call
external_temporal_service_or_worker_startup
live_or_default_on_behavior
public_webhook_exposure
automatic_replies
worker_auto_routing
agent_to_agent_auto_routing
@all_fanout
trusted_markdown_html_rendering
```

These remain blocked regardless of this packet landing. A design packet does not approve implementation; local/offline design does not approve live, Gateway, or real-delivery behavior.

## Future Implementation Phases

### Next allowed request — local/offline implementation only

```text
approve_agent_run_supervisor_sachima_local_offline_integration_implementation_no_live_no_gateway_no_real_delivery
```

Scope a later local/offline implementation would cover: a default-off caller seam that builds a `CallerInvocationSpec`, calls `invoke_caller` (starting with dry-run/config-preview), maps `CallerResult` into a caller-owned offline view model, and writes sanitized local evidence — with local-only tests, no-leak/no-secret probes, and a changed-file guard. It would **not** approve live behavior, Gateway involvement, real ingress, or real delivery.

### Later, separately named approvals (each needs its own packet)

- **Controlled AI FLOW execution** (P6 direction): a separate approval such as
  `approve_sachima_controlled_ai_flow_supervised_local_agent_execution_no_live_no_real_delivery`,
  after the local/offline implementation evidence and the P5 durable-runtime ownership design.
- **Live / Gateway presentation surface:** a separate approval, after a fresh threat model, for any Gateway presentation/ingress role, real delivery, or live/default-on behavior. Naming the Gateway as a caller or delivery surface is out of scope until then.

## Acceptance Checklist

- [ ] Status markers present: `DESIGN_ONLY`, `IMPLEMENTATION_NOT_APPROVED`, `LIVE_NOT_APPROVED`, `GATEWAY_NOT_APPROVED`, `REAL_DELIVERY_NOT_APPROVED`.
- [ ] Approval token quoted verbatim and framed as local/offline integration design only.
- [ ] Goal-trace chain present (final goal → gap → phase → task → test → evidence → decision).
- [ ] Core design decision states caller is a local Sachima/FlowWeaver/Hermes controller/Activity, not the Gateway; supervisor stays a local library/evidence layer.
- [ ] Architecture text diagram ends at "no real delivery".
- [ ] Caller-owned input contract and output contract preserve the ownership split; `business_verdict` stays `None` from the library.
- [ ] Mode mapping covers exec, session, dry-run/config-preview, and status/close/cancel, with cancellation/rollback marked as future concerns.
- [ ] FlowWeaver integration plan uses claim-check refs, no-throw wrappers, evidence-only local probe; durable query/update/cancel deferred.
- [ ] Safety/no-leak boundary list present and complete.
- [ ] Explicit non-approvals list present and intact.
- [ ] Next approval texts (local/offline implementation; later controlled AI FLOW / live) present.
- [ ] Changed files limited to `docs/plans/`, `docs/dev_log/`, and `docs/roadmap/current-status.md`.
- [ ] `git diff --check` clean; no secrets, no raw logs, no token values.

## Scoring Rubric

| Category | Points |
|---|---:|
| Scope clarity and non-approval separation (local/offline only; Gateway deferred) | 20 |
| Ownership-split accuracy (caller vs supervisor library; `business_verdict` stays `None`) | 20 |
| Contract and mode-mapping completeness (input/output/exec/session/dry-run/cancel-deferred) | 20 |
| No-leak / claim-check / no-throw boundary quality | 20 |
| Goal-trace, evidence-input accuracy, and handoff/next-approval quality | 20 |

Pass threshold: **92/100**, with automatic failure on any wording that implies implementation approval, live/default-on behavior, Gateway as the concrete caller or delivery surface, real external ingress, real IM/Feishu delivery, production config writes, Gateway-owned lifecycle, automatic replies, worker/agent-to-agent auto-routing, `@all` fanout, or trusted Markdown/HTML rendering.

## Decision Outcome

If this packet passes the docs gate and both reviews:

```text
agent_run_supervisor_sachima_local_offline_integration_design_ready_for_separate_local_offline_implementation_request
```

Next allowed request:

```text
approve_agent_run_supervisor_sachima_local_offline_integration_implementation_no_live_no_gateway_no_real_delivery
```

Still not approved (carried):

```text
real_external_sachima_ingress
real_external_delivery
production_delivery_control
production_agent_tool_execution_expansion
production_config_write
gateway_restart_or_reload
platform_adapter_mutation
gateway_owned_temporal_lifecycle
real_send_api_or_external_im_call
external_temporal_service_or_worker_startup
live_or_default_on_behavior
public_webhook_exposure
automatic_replies
worker_auto_routing
agent_to_agent_auto_routing
@all_fanout
trusted_markdown_html_rendering
```
