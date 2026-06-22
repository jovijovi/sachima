# Sachima Final Goal Gap Analysis

## Purpose

This document turns the final Sachima project goal into a practical planning baseline. It records what is already proven, what is still missing, which gaps block the final AI workbench experience, and which phase sequence should guide future development.

Canonical goal summary:

```text
Sachima should become Dog Brother's own AI workbench inside a custom IM channel: a safe, durable, observable, and recoverable Hermes/FlowWeaver system that can receive real IM requests, orchestrate long AI workflows, deliver results back through the channel, and preserve clear operational control.
```

## Current verified baseline

### Sachima channel

Already present:

- `Platform.SACHIMA` is registered as `sachima`.
- `SachimaAdapter` can convert webhook payloads into Hermes `MessageEvent` objects.
- Adapter-owned inbound HTTP webhook listener exists.
- HMAC signing and idempotency are documented.
- Text replies can be locally recorded when no external send API is configured.
- Image ingress supports controlled image attachment shapes with safety checks.
- Local adapter-level and GatewayRunner smoke scripts exist.

Still constrained:

- Production-adjacent PE-1 evidence uses loopback ingress only.
- `SACHIMA_SEND_URL` remains absent in PE-1 observation runs.
- Real external IM ingress and real outbound delivery remain unapproved.

### FlowWeaver / durable orchestration

Already proven across prior phases:

- Transaction / Intent / Operation / Artifact / Delivery model is established.
- Artifact and delivery surfaces are separated.
- Delivery/ACK reconciliation has local proof.
- Controlled agent execution Activity boundaries have local proof.
- AI FLOW pilot produced sanitized snapshots and decision packets.
- Production-shadow observation sidecar is default-off, Sachima-only in PE-1, observation-only, and start/query-only.
- Rollback by disabling `flowweaver.production_shadow_observation.enabled` has been drilled and restored.

Still constrained:

- Production PE-1 uses a file runtime hook, not a production Temporal Worker.
- Production agent/tool execution expansion is not enabled.
- Production delivery control and ACK reconciliation are not enabled.
- PE-2 implementation and live/default-on remain NO-GO.

## Gap summary table

| Area | Current state | Final target | Gap severity | Next planning implication |
|---|---|---|---:|---|
| Real external Sachima ingress | Loopback-only controlled webhook | Real IM ingress through an approved exposure boundary | High | Needs separate external-ingress design, threat model, rollback, and approval. |
| Outbound delivery | Local recording or absent send URL in PE-1 | Real text/card/media delivery with ACK tracking | High | Add fake-send / simulator UI loop before real send API. |
| Durable runtime | File runtime hook, start/query-only observation | Production Temporal/durable runtime with query/update/retry/cancel/recover | High | Design runtime ownership and deployment separately; Gateway must not own lifecycle silently. |
| Agent/tool execution | Local controlled Activity evidence | Production-safe AI FLOW execution from Sachima requests | High | Requires claim-check inputs, no-throw Activities, policy gates, and operator approvals. |
| Delivery/ACK closure | Local reconciliation evidence | Production ACKs tied to initialized delivery slots | High | Need fake-send evidence, exact slot mapping, duplicate/replay probes. |
| Product UX | Text docs and evidence packets | IM task cards, progress, approvals, artifacts, pause/resume/rollback | Medium | Design high-density task card schema and simulator UX before live. |
| Observability | Evidence JSON/Markdown and manual checks | Ongoing metrics, alerts, dashboards, auto evidence packets | Medium | Add operational telemetry and evidence extraction only after scope is stable. |
| Security/no-leak | Strong PE-1 no-leak gates | Sustained no-leak across real ingress/delivery/runtime | High | Expand no-leak scanners to fake-send transcripts, runtime history bytes, logs, and user-visible cards. |
| Operator workflow | Manual approvals and runbooks | Repeatable start/pause/rollback/restore procedure | Medium | Promote PE-1C rollback drill into operator runbook for later phases. |
| Multi-user / permissions | Narrow local allowed user | Real operator/user/group policy | Medium | Separate auth/allowlist model before real external ingress. |

## Detailed gaps

### 1. External Sachima ingress

The project is not yet at real external ingress. The current safe path is a loopback listener and controlled signed webhook probes. This is correct for PE-1, but final usage needs a real IM system or reverse proxy to reach Sachima.

Required before external ingress:

- exact exposure design: host, path, reverse proxy, TLS, rate limits, request body limits;
- HMAC and timestamp replay policy;
- allowlist model for users/groups;
- duplicate and retry semantics under real network behavior;
- SSRF/media limits for real image URLs;
- rollback procedure that stops ingress without touching raw payloads;
- fresh-context security review.

Do not combine external ingress with PE-2 implementation or real delivery control. That would create too many moving parts at once.

### 2. Fake-send / simulator delivery loop

The safest next behavior-bearing proof before real outbound delivery is a fake-send or simulator UI loop. PE-1 intentionally kept `SACHIMA_SEND_URL` absent. Final Sachima needs real response delivery, but the system should first prove the delivery path against a local fake target.

Required proof:

- adapter sends to a fake local `/send` endpoint;
- simulator stores and renders assistant replies;
- final text, progress card, rich card, media, and artifacts remain separate surfaces;
- ACKs are generated only from real fake-send responses, never invented;
- duplicate/replay send attempts are idempotent;
- no raw prompt/card/media/tool output leaks into evidence or durable state;
- user-visible cards use high-density intent summaries, never raw text fallback.

### 3. Production durable runtime

The final system needs a durable runtime, likely Temporal, to survive long workflows, retries, and restarts. The current PE-1 runtime hook proves observation only and deliberately avoids owning Temporal lifecycle inside Gateway.

Required design decisions:

- who owns the Temporal service and Worker lifecycle;
- namespace/task queue naming and deployment model;
- start/query/update/reconcile contract;
- cancellation and pause/resume semantics;
- no-throw Activity wrappers for all plugin/caller-supplied Activities;
- serialized history no-leak checks, including protobuf bytes, not just JSON text;
- replay and duplicate-start behavior;
- metrics and alerting.

The Gateway should keep using a caller-supplied runtime surface. It should not create hidden Temporal clients or Workers as a side effect of message handling.

### 4. Production agent/tool execution

The final AI workbench requires real AI FLOW execution: planning, tool calls, code edits, tests, PRs, CI wait, merge coordination, and final reports. The project has local controlled Activity evidence, but production execution from Sachima is still blocked.

Required before enabling:

- claim-check references for all raw user/platform material;
- exact policy for which tools can run from Sachima-originated workflows;
- approval gates for side effects such as file writes, git pushes, PR merges, messages, external APIs;
- sanitized progress snapshots;
- timeout/cancellation handling;
- no raw exception text in history, logs, or user-facing cards;
- red-team probes for malicious payloads and hostile object/value shapes.

### 5. Delivery/ACK production closure

Final delivery is not just sending a response. It must prove what was delivered, on which surface, and whether it was acknowledged or failed.

Required before production closure:

- delivery slots initialized before ACK updates;
- emitted ACK targets are a deterministic subset/prefix of initialized slots;
- rich-card delivery never suppresses final text;
- media delivery is tracked separately from text/card delivery;
- duplicate ACK updates are safe;
- failed sends produce stable error codes without raw platform payload leakage;
- UI and evidence distinguish `progress_card_sent`, `rich_cards_sent`, `final_text_sent`, and `media_sent`.

### 6. Product surface and operator experience

The final product should feel like a workbench, not a stream of logs. Sachima should present tasks as compact stateful artifacts.

Required product features:

- high-density intent summary cards;
- progress updates with current phase, next action, and blocker reason;
- approval buttons or equivalent approval commands;
- artifact list with safe refs and labels;
- pause/resume/cancel/rollback actions;
- final summary with verification evidence;
- concise error recovery messages.

The product rule is: user-facing cards summarize intent and state; they do not dump raw payloads, raw logs, or huge JSON.

### 7. Operational maturity

PE-1C proved rollback for the observation flag. The final system needs broader operational discipline.

Required operations:

- start/pause/rollback/restore runbooks per phase;
- evidence packet generator;
- no-leak scanner for docs, logs, runtime state, cards, and histories;
- metrics for starts, failures, timeouts, duplicates, delivery results, and rollback state;
- alert thresholds;
- staged rollout windows;
- post-incident review template.

## Recommended phase sequence

### Phase A — PE-1D longer controlled local observation

Goal: increase confidence in observation-only Sachima ingress without expanding scope.

Scope:

- loopback-only Sachima webhook;
- HMAC required;
- narrow local allowed user;
- `SACHIMA_SEND_URL` absent;
- repeated positive turns plus negative probes;
- no Temporal Worker/service;
- evidence packet and no-leak scan.

Exit criteria:

- expected observation/workflow deltas only for allowlisted turns;
- no raw material in shadow files/evidence;
- duplicate/replay probes do not create extra state;
- rollback remains exact and fast.

### Phase B — Fake-send / simulator UI loop

Goal: prove delivery behavior without real external delivery.

Positioning: fake-send is a required evidence step before PE-2 implementation or real delivery control. A PE-2 design packet may be drafted before or after this phase, but it must treat fake-send evidence as a blocker for implementation and live-facing delivery behavior.

Scope:

- fake local send target;
- simulator transcript or UI;
- final text/rich card/progress/media surface separation;
- ACK mapping from fake send responses only;
- no real external IM calls.

Exit criteria:

- assistant event appears in simulator;
- delivery state matches fake send responses;
- rich card does not suppress final text;
- no raw payload or secret appears in transcripts/evidence.

### Phase C — PE-2 design packet only

Goal: define the smallest PE-2 behavior-bearing step based on PE-1D and fake-send evidence.

Scope:

- docs/design only;
- no implementation;
- no live/default-on;
- no real external ingress;
- exact approvals listed separately.

Exit criteria:

- explicit PE-2 contract;
- concrete non-approvals;
- fresh-context reviews with zero blockers.

### Phase D — Controlled external ingress design and implementation

Goal: expose Sachima ingress beyond loopback without delivery or agent execution expansion.

Scope:

- approved external ingress only;
- strict auth/rate/body/media limits;
- observation-only or simulator-only behavior;
- rollback and monitoring.

Exit criteria:

- external signed request path works;
- negative probes fail closed;
- no real delivery or agent execution unless separately approved.

### Phase E — Production durable runtime integration

Goal: attach a real durable runtime behind a caller-supplied control surface.

Scope:

- runtime owner is explicit;
- Gateway does not own lifecycle implicitly;
- start/query/update contracts are sanitized;
- no-throw Activity wrappers;
- replay/history no-leak.

Exit criteria:

- restart/retry/replay evidence;
- query snapshots stable;
- no-leak history checks pass.

### Phase F — Controlled AI FLOW execution

Goal: allow selected long AI workflows from Sachima with approvals and sanitized state.

Scope:

- limited toolset and side-effect policy;
- claim-check raw inputs;
- approvals for risky actions;
- progress cards and artifacts;
- cancellation/rollback.

Exit criteria:

- end-to-end task completes through Sachima;
- PR/CI/artifact evidence is linked safely;
- operator can pause/cancel/recover.

### Phase G — Real delivery and ACK closure

Goal: connect real delivery and ACKs after fake-send and runtime contracts are proven.

Scope:

- real send API;
- delivery slot initialization;
- ACK reconciliation;
- retry/error handling;
- final text/card/media separation.

Exit criteria:

- real messages deliver correctly;
- ACKs match initialized slots;
- failures are stable-code only;
- no duplicated/suppressed final response.

## Recommended planning heuristics

1. Keep each phase behavior-bearing. Avoid pure report-only phases unless they gate a real risk.
2. Change one axis at a time: ingress, delivery, runtime, agent execution, and UX should not all move in the same PR.
3. Every phase should have a rollback drill or an explicit rollback proof.
4. Every user-visible surface must prefer high-density summaries over raw logs or raw payloads.
5. Every decision packet should list non-approvals as clearly as approvals.
6. Every production-adjacent phase should include fresh-context blocker reviews.
7. Evidence packets should be safe to paste into IM without redaction.

## Current progress estimate

These are planning estimates, not release promises:

| Dimension | Approximate progress | Notes |
|---|---:|---|
| Architecture direction | 80% | Core model and boundaries are coherent. |
| Safety boundary discipline | 75% | PE-1 proved strong fail-closed/no-leak/rollback behavior. |
| Sachima base channel | 60% | Adapter, auth, media, and local smoke exist; real external ingress/delivery pending. |
| Production FlowWeaver readiness | 40% | Local proofs are strong; production durable runtime and execution are pending. |
| Final AI workbench UX | 25% | Product surface and operator experience still need design/build. |

Overall distance to the final goal is roughly halfway: the foundation is real, but the system is not yet a live, full-capability AI workbench.
