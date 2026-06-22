# P4 Agentic-UI Controlled External Ingress Design Packet

> Scope: docs/design only. This packet canonicalizes Sachima Envelope v1 and defines the safe bridge plan for using agentic-ui as the first external client conformance target.
>
> Stable marker: **No implementation** is approved by this packet.

## 1. Goal

Establish a formal Sachima-controlled external wire protocol before any implementation or live ingress work proceeds.

This packet turns the current protocol discussion into a reviewable P4 design basis:

- canonical protocol: `docs/protocols/sachima-envelope-v1.md`;
- client conformance target: `jovijovi/agentic-ui` branch `epic/phase-5-production-readiness`;
- phase boundary: P4 controlled external ingress design packet only;
- next work after merge: separately approved implementation/conformance tests, still no live/default-on behavior.

## 2. Current phase position

From `docs/roadmap/current-status.md` at the start of this work:

```text
current_position: P4 next — Controlled external ingress design packet
next_allowed_request: P4 controlled external ingress design packet only
```

This packet is allowed because it is design/protocol work only. It does not implement external ingress.

## 3. Explicit non-approvals

This packet does not approve:

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
reverse_proxy_or_tls_config_write
```

## 4. Design decision

Decision:

```text
Sachima owns the external wire protocol.
agentic-ui is the first conformance target.
Sachima Envelope v1 is the canonical protocol basis for P4 controlled external ingress design.
```

Rationale:

1. Sachima is the Gateway/channel layer and must support more than one external client.
2. agentic-ui is under development and should adapt to the canonical channel contract rather than preserve a mock-only shape.
3. A canonical v1 protocol prevents `text`/`content`, seconds/milliseconds, and send/delivery URL ambiguity from freezing into production.
4. agentic-ui still owns its internal UI/SSE/store model; those internals must not leak into the Sachima protocol authority.

## 5. Reviewer meeting summary

The protocol proposal was reviewed independently by Codex and Claude Code before this packet.

| Reviewer | Verdict | Accepted findings |
|---|---|---|
| Codex | PASS | Support Sachima as protocol owner; require 2xx callback semantics to mean receiver accepted only; require HMAC/schema/no-leak probes. |
| Claude Code | PASS with required fixes | Timestamp unit mismatch, Sachima outbound HMAC, and `content` → `text` migration are hard interop issues that must be in the design packet. |

No reviewer rejected the core decision. The accepted blockers are design requirements for future implementation, not blockers to landing the design packet.

## 6. Known compatibility gaps this packet resolves

| Gap | Current state | v1 decision |
|---|---|---|
| Protocol ownership | agentic-ui has a mock bridge spec; Sachima has current adapter behavior. | Canonical protocol lives in Sachima under `docs/protocols/`. |
| HMAC timestamp | agentic-ui uses Unix milliseconds; Sachima validates Unix seconds. | v1 uses Unix seconds. Milliseconds are rejected. |
| Text field name | agentic-ui outbound uses `content`; Sachima ingress reads `text`. | v1 canonical field is `text`; `content` is DEPRECATED migration alias only. |
| Delivery callback auth | Sachima outbound `send()` currently lacks v1 HMAC headers. | Future implementation must sign delivery callbacks with the same HMAC algorithm. |
| ACK meaning | Callback success could be overread as user-visible delivery. | HTTP 2xx means callback accepted by receiver only. P7 owns real delivery/ACK closure. |
| Env direction | `SACHIMA_SEND_URL` is ambiguous across sides. | Long-term names split `SACHIMA_INGRESS_URL` and `SACHIMA_DELIVERY_URL`; old name deprecated. |

## 7. v1 implementation requirements for a later phase

A later implementation request must be explicit and must remain narrower than live/default-on unless separately approved.

Minimum Sachima-side implementation requirements:

- validate `schema_version: sachima.v1`;
- require `message_id`, `chat_id`, `user_id`, direction-specific `role`, and canonical `text` where applicable;
- reject Unix-millisecond HMAC timestamps;
- sign delivery callbacks with `X-Sachima-Timestamp` and `X-Sachima-Signature`;
- add `SACHIMA_DELIVERY_URL` with documented precedence over deprecated `SACHIMA_SEND_URL`;
- keep secretless operation dev-only and fail closed for controlled external ingress;
- preserve allowlist, duplicate, body/media, and no-leak behavior.

Minimum agentic-ui-side implementation requirements:

- send v1 ingress envelopes to `SACHIMA_INGRESS_URL`;
- use Unix seconds HMAC;
- generate stable `message_id` values;
- include stable `user_id` values;
- emit canonical `text` instead of `content`;
- accept v1 delivery callbacks only with valid HMAC;
- map v1 delivery callbacks into agentic-ui internal SSE/store state;
- align its mock server with v1 rather than treating the mock shape as canonical.

## 8. Required future conformance probes

Before any implementation can claim P4 progress, it must include probes for:

- valid seconds timestamp accepted;
- Unix-millisecond timestamp rejected;
- stale timestamp rejected;
- future timestamp rejected;
- missing signature rejected;
- tampered raw body rejected;
- JSON reserialization mismatch rejected;
- missing required fields rejected;
- unknown `schema_version` rejected;
- invalid direction-specific `role` rejected;
- duplicate `message_id` deduplicated without duplicate side effects;
- disallowed `user_id` / group rejected;
- oversized body rejected;
- malformed image rejected if media is accepted;
- URL-backed image SSRF/private network rejection if URL media is accepted;
- Sachima delivery callback includes v1 HMAC headers;
- no raw body, secret, media bytes/path, card JSON, raw exception text, or unsafe platform identifier leaks into logs, durable evidence, or user-visible output.

## 9. Local-only first execution model

The first implementation/conformance phase should be local-only:

```text
agentic-ui dev BFF -> loopback Sachima ingress -> Hermes fake/controlled path -> loopback agentic-ui delivery callback -> agentic-ui internal SSE/store
```

The exact port/path must be selected without killing or restarting an existing Gateway. If default port `8788` is occupied, use an isolated fallback and record the deviation as a WATCH item.

Public tunnel, reverse proxy, TLS, and real external exposure remain separate approvals.

## 10. Acceptance checklist for this design packet

- [x] Canonical protocol path selected: `docs/protocols/sachima-envelope-v1.md`.
- [x] Protocol ownership and client conformance roles documented.
- [x] HMAC seconds decision documented.
- [x] `text` vs `content` migration documented.
- [x] Delivery callback HMAC requirement documented.
- [x] 2xx callback semantics limited to receiver acceptance.
- [x] Env naming direction clarified.
- [x] Future conformance probes listed.
- [x] Explicit non-approvals preserved.
- [x] Independent reviewer findings incorporated.

## 11. Score

| Category | Points | Evidence |
|---|---:|---|
| Scope clarity | 20/20 | Docs-only packet; non-approvals explicit. |
| Evidence dependency accuracy | 20/20 | Uses current Sachima adapter facts and agentic-ui Phase 5 bridge facts. |
| Testability of future implementation plan | 20/20 | Required future probes are concrete and direction-specific. |
| Approval/non-approval separation | 20/20 | Implementation/live/config/restart/delivery remain blocked. |
| Reviewability and handoff quality | 20/20 | Canonical protocol, design packet, dev log, and roadmap status are linked. |

Design packet score: **100/100**.

This score is for the design packet only. It is not a production readiness score.

## 12. Next allowed request after this packet

If this packet merges and current-status is updated, the next recommended request is a separately approved implementation/conformance phase, for example:

```text
approve_p4_sachima_envelope_v1_local_conformance_implementation_no_live_no_public_ingress_no_real_delivery
```

That future request would still not approve production config writes, Gateway restart/reload, public webhook exposure, real external delivery, or live/default-on behavior.
