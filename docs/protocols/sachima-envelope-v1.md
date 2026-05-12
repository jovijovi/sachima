# Sachima Envelope v1

> Canonical external wire protocol for Sachima-controlled ingress and delivery callbacks.
>
> Status: design-canonical for P4 controlled external ingress design packet.
> This document is protocol authority. Client repositories may document adaptation details, but they must cite this file rather than redefining the wire contract.

## 1. Ownership and scope

Sachima owns this external wire protocol because Sachima is the Gateway/channel boundary. External clients such as agentic-ui are conformance targets: they adapt to this contract and may feed back requirements, but they do not own the canonical field names, signing rules, or acceptance gates.

This v1 contract covers two HTTP JSON surfaces:

1. **Ingress:** external client → Sachima/Hermes, carrying a user-originated request.
2. **Delivery callback:** Sachima/Hermes → external client, carrying an assistant-originated result or update accepted by the external receiver.

This contract does **not** approve public exposure, production configuration writes, Gateway restart/reload, platform adapter mutation, live/default-on behavior, real external delivery, real IM sends, or production AI/tool execution expansion. Those remain separately approved phases.

## 2. Normative keywords

The words **MUST**, **MUST NOT**, **SHOULD**, **MAY**, and **DEPRECATED** are normative.

## 3. Shared transport requirements

Both ingress and delivery callback requests MUST use:

- `Content-Type: application/json`;
- UTF-8 JSON body;
- HMAC headers defined in Section 4;
- request body size limits defined by the deployment runbook;
- fail-closed behavior on malformed JSON, missing required fields, invalid signature, stale/future timestamp, replay, or disallowed user/group.

Receivers MUST validate using the raw request body bytes/string that were signed. Receivers MUST NOT parse JSON and serialize it again before HMAC verification.

## 4. HMAC signing

### 4.1 Headers

```text
X-Sachima-Timestamp: <unix-seconds>
X-Sachima-Signature: <hex-hmac-sha256>
```

### 4.2 Algorithm

```text
signature = hex(hmac_sha256(secret, "{timestamp}.{raw_body}"))
```

Where:

- `timestamp` is an integer Unix timestamp in **seconds**.
- `raw_body` is the exact JSON request body as transmitted.
- `secret` is the shared HMAC secret configured out-of-band.

### 4.3 Freshness

Receivers MUST reject timestamps outside the configured tolerance window. The default tolerance is 300 seconds.

Receivers MUST reject:

- missing timestamp;
- non-integer timestamp;
- Unix-millisecond timestamp;
- stale timestamp;
- far-future timestamp;
- missing signature;
- malformed signature;
- signature mismatch;
- signature generated over a JSON-reserialized body instead of the raw body.

### 4.4 Unsigned requests

Production and controlled external ingress MUST reject unsigned requests.

A secretless mode MAY exist only for explicitly local dev/fake harnesses, and it MUST be named as dev-only in configuration and evidence. Secretless mode MUST NOT be inferred from this protocol.

## 5. Envelope identity and idempotency

Every v1 envelope MUST include:

- `schema_version` exactly equal to `sachima.v1`;
- `message_id`, a stable idempotency key scoped by sender and channel;
- `chat_id`, the conversation/session/room identifier;
- `user_id`, the end-user or sender identifier;
- `role`, constrained by the direction-specific rules below;
- `text`, when the envelope carries text content.

Receivers MUST deduplicate by a stable key that includes at least `message_id` and enough source context to prevent collisions across chats or clients. Duplicate requests MUST NOT create duplicate agent execution, duplicate delivery, or duplicate ACK state.

`message_id` SHOULD be globally unique within the external client or Sachima deployment. UUIDv4/ULID-style values are acceptable. The protocol does not require a specific ID algorithm, but implementations MUST reject empty IDs and IDs exceeding documented length limits.

## 6. External client → Sachima ingress

### 6.1 Purpose

Ingress carries a user-originated request from an external client into Sachima/Hermes.

### 6.2 Canonical payload

```json
{
  "schema_version": "sachima.v1",
  "message_id": "client-generated-id",
  "chat_id": "conversation-or-session-id",
  "user_id": "end-user-id",
  "role": "user",
  "text": "user message",
  "chat_type": "private",
  "thread_id": null,
  "reply_to_message_id": null,
  "attachments": [],
  "metadata": {}
}
```

### 6.3 Required fields

| Field | Required | Rule |
|---|---:|---|
| `schema_version` | Yes | MUST be `sachima.v1`. |
| `message_id` | Yes | Non-empty string, documented max length. |
| `chat_id` | Yes | Non-empty string, documented max length. |
| `user_id` | Yes | Non-empty string, documented max length. |
| `role` | Yes | MUST be `user` for ingress. |
| `text` | Conditional | Required unless supported attachments carry the user content. |
| `chat_type` | No | SHOULD be `private`, `group`, or `channel` when known. |
| `thread_id` | No | Optional sub-thread or topic identifier. |
| `reply_to_message_id` | No | Optional parent message ID. |
| `attachments` | No | Optional; v1 supports image attachments only. |
| `metadata` | No | Optional implementation-specific object. |

### 6.4 `text` vs `content`

The canonical text field is `text`.

`content` is DEPRECATED and MAY be accepted only as a migration alias during a documented compatibility window. If accepted, it MUST be normalized to `text` before validation, dispatch, evidence writing, or delivery state creation. New clients MUST NOT emit `content` as the canonical field.

### 6.5 Attachments

v1 supports image attachments only. A receiver that accepts attachments MUST enforce:

- explicit image MIME allowlist;
- decoded size limit;
- encoded size guard;
- base64 validation;
- URL attachment SSRF controls if URL-backed images are accepted;
- no raw media bytes or local media paths in durable evidence.

Non-image attachments are reserved for later protocol versions unless a separate approval and implementation plan explicitly adds them.

### 6.6 Ingress responses

Receivers SHOULD respond with JSON.

| HTTP | Meaning | Body shape |
|---:|---|---|
| 2xx | Accepted by Sachima receiver | `{ "ok": true, "message_id": "..." }` |
| 2xx | Duplicate already accepted | `{ "ok": true, "duplicate": true }` |
| 400 | Invalid payload | `{ "ok": false, "error": "invalid_payload" }` |
| 401 | Invalid signature / replay window | `{ "ok": false, "error": "invalid_signature" }` |
| 403 | Disallowed user/group/client | `{ "ok": false, "error": "forbidden" }` |
| 413 | Body/media too large | `{ "ok": false, "error": "payload_too_large" }` |
| 429 | Rate limited | `{ "ok": false, "error": "rate_limited" }` |
| 5xx | Receiver unavailable/internal failure | `{ "ok": false, "error": "unavailable" }` or `{ "ok": false, "error": "internal" }` |

Error details MUST be sanitized. They MUST NOT contain raw request bodies, secrets, raw platform IDs beyond allowed stable identifiers, raw media bytes/paths, card JSON, or raw exception text.

## 7. Sachima → external client delivery callback

### 7.1 Purpose

Delivery callback carries assistant-originated output from Sachima/Hermes to an external client receiver.

A successful HTTP 2xx response from the external client means only:

```text
callback accepted by receiver
```

It does not prove browser-visible rendering, user-visible delivery, real IM delivery, or ACK closure. Those are later delivery/ACK phases.

### 7.2 Canonical payload

```json
{
  "schema_version": "sachima.v1",
  "message_id": "sachima-generated-id",
  "chat_id": "same-chat-id",
  "user_id": "sachima-hermes",
  "role": "assistant",
  "text": "assistant reply",
  "reply_to_message_id": "original-user-message-id",
  "metadata": {
    "workflow_id": "stable-workflow-ref",
    "transaction_id": "stable-transaction-ref",
    "delivery_ref": "stable-delivery-ref",
    "ack_ref": "stable-ack-ref"
  }
}
```

### 7.3 Required fields

| Field | Required | Rule |
|---|---:|---|
| `schema_version` | Yes | MUST be `sachima.v1`. |
| `message_id` | Yes | Sachima-generated or Sachima-stable idempotency key. |
| `chat_id` | Yes | MUST target the same logical chat/session. |
| `user_id` | Yes | MUST identify the assistant/backend sender, e.g. `sachima-hermes`. |
| `role` | Yes | MUST be `assistant` for delivery callbacks. |
| `text` | Conditional | Required for final/progress text surfaces unless a future approved media/artifact surface replaces it. |
| `reply_to_message_id` | No | SHOULD reference the triggering user message when available. |
| `metadata` | No | SHOULD carry stable sanitized refs for workflow/transaction/delivery/ACK correlation. |

### 7.4 Delivery callback responses

The external client receiver SHOULD return JSON.

| HTTP | Meaning |
|---:|---|
| 2xx | Callback accepted by receiver. |
| 400 | Invalid payload; do not retry without a code/config change. |
| 401 | Invalid signature. |
| 403 | Receiver refuses this chat/user/client. |
| 409 | Duplicate/conflict according to receiver idempotency rules. |
| 413 | Payload too large. |
| 429 | Retryable rate limit if the receiver declares retry semantics. |
| 5xx | Retryable receiver/server failure. |

## 8. Environment naming

Direction-specific names MUST avoid the ambiguous term “send” as the long-term canonical name.

### 8.1 Sachima / Gateway side

| Variable | Meaning |
|---|---|
| `SACHIMA_WEBHOOK_HOST` | Host/interface for Sachima ingress listener. |
| `SACHIMA_WEBHOOK_PORT` | Port for Sachima ingress listener. |
| `SACHIMA_WEBHOOK_PATH` | Path for Sachima ingress listener. |
| `SACHIMA_WEBHOOK_SECRET` | Shared HMAC secret for v1 requests. |
| `SACHIMA_DELIVERY_URL` | External client callback URL for Sachima → client delivery. |
| `SACHIMA_ALLOWED_USERS` | Allowlist for ingress users. |

`SACHIMA_SEND_URL` is DEPRECATED as an alias for `SACHIMA_DELIVERY_URL`. During migration, precedence and warning behavior MUST be documented and tested.

### 8.2 External client side

| Variable | Meaning |
|---|---|
| `SACHIMA_INGRESS_URL` | Sachima ingress endpoint for external client → Sachima requests. |
| `SACHIMA_WEBHOOK_SECRET` | Shared HMAC secret for v1 requests. |
| `NEXT_PUBLIC_USE_SACHIMA` | agentic-ui UI feature flag, if applicable; not part of the Sachima protocol. |

Client-specific UI/SSE/runtime variables are not part of this protocol.

## 9. Migration behavior

Implementations moving from pre-v1 mock or local-only shapes SHOULD follow this order:

1. Add v1 validators and fixtures without changing live behavior.
2. Add seconds-based HMAC fixtures for both directions.
3. Add delivery-callback HMAC signing to Sachima.
4. Add `text` canonicalization and DEPRECATED `content` alias handling under tests.
5. Add `schema_version` and `role` validation.
6. Add local-only cross-repo conformance probes.
7. Only after separate approval, run controlled external ingress probes.

No migration step approves public exposure, default-on behavior, production config writes, Gateway restart/reload, or real external delivery.

## 10. Required conformance probes

A v1 implementation cannot pass without probes for:

- valid seconds timestamp accepted;
- Unix-millisecond timestamp rejected;
- stale timestamp rejected;
- future timestamp rejected;
- missing signature rejected;
- tampered body rejected;
- JSON reserialization mismatch rejected;
- missing required field rejected;
- unknown `schema_version` rejected;
- invalid direction-specific `role` rejected;
- duplicate `message_id` deduplicated without duplicate side effects;
- disallowed `user_id` / group rejected;
- oversized body rejected;
- malformed image rejected when media is accepted;
- private/internal URL-backed media rejected when URL media is accepted;
- Sachima delivery callback includes HMAC headers;
- no raw body, secret, media bytes/path, card JSON, raw exception text, or unsafe platform identifier leaks into logs/evidence/user-visible output.

## 11. agentic-ui conformance position

agentic-ui is the first known external client conformance target for this protocol. Its internal SSE envelope, React state model, feature flag, pseudo-streaming, and artifact rendering are client internals. They MUST NOT become Sachima wire-protocol authority.

agentic-ui adaptation SHOULD:

- send v1 ingress envelopes to `SACHIMA_INGRESS_URL`;
- use Unix seconds for HMAC headers;
- generate stable client `message_id` values;
- include stable `user_id` values;
- use canonical `text`;
- accept v1 delivery callbacks from Sachima with HMAC verification;
- map v1 delivery callbacks into its internal SSE/store model;
- keep mock server behavior aligned with v1 rather than preserving a divergent mock-only protocol.

## 12. Open design tails

| Tail | Class | Meaning | Required before |
|---|---|---|---|
| `SACHIMA-ENV-V1-IMPLEMENTATION` | NEXT_PHASE | Implement v1 validators/signing/adapters in Sachima and agentic-ui. | Any controlled external ingress implementation claim. |
| `SACHIMA-ENV-V1-DELIVERY-ACK` | PARKED | Browser-visible/user-visible delivery ACK is not proven by callback 2xx. | P7 real delivery and ACK closure. |
| `SACHIMA-ENV-V1-MULTI-MEDIA` | PARKED | Non-image media and richer artifact surfaces are out of v1 unless separately approved. | Future protocol version or explicitly approved extension. |

## 13. Decision summary

Decision:

```text
Sachima owns the external wire protocol.
agentic-ui is the first conformance target.
Sachima Envelope v1 is the canonical protocol basis for P4 controlled external ingress design.
```

Rejected alternatives:

- Letting agentic-ui mock protocol become canonical: rejected because client-specific mocks would pull the Gateway/channel contract into a UI repository.
- Preserving ambiguous `content` / `send_url` as canonical names: rejected because they obscure direction and drift from current Sachima ingress behavior.
- Treating callback 2xx as final user delivery: rejected because receiver acceptance is not browser-visible or IM-visible delivery.
