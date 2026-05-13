# Sachima Custom IM Channel

Sachima is a minimal native Hermes gateway platform for experimenting with a custom IM channel.

## Status

Current first slice:

- Registers `Platform.SACHIMA` with value `sachima`.
- Enables config via `SACHIMA_ENABLED=true`.
- Adds `gateway.platforms.sachima.SachimaAdapter`.
- Converts generic webhook payloads into Hermes `MessageEvent` objects.
- Supports local outbound-message recording when no external send API is configured.
- Wires `GatewayRunner._create_adapter()` to construct the adapter.
- Adds a platform prompt hint for Sachima text IM replies.
- Registers Sachima in Hermes platform/toolset metadata so real agent runs can resolve default tools.
- Includes local adapter-level and real `GatewayRunner` smoke scripts.

The adapter now runs an adapter-owned inbound HTTP webhook listener from `connect()`. Embedding code can still call `build_event_from_payload()` / `handle_webhook_payload()` directly for tests or bridge development.

## Protocol status

The adapter now has Sachima-side local conformance for Sachima Envelope v1. For controlled external ingress and delivery callback design, the canonical wire contract is:

- `jovijovi/sachima-protocols` → `protocols/envelope/v1.md`
- local pointer: `docs/protocols/sachima-envelope-v1.md`

This file remains useful as implementation-facing adapter documentation. The local implementation does not approve public exposure, production configuration writes, Gateway restart/reload, live/default-on behavior, or real external delivery.

## Environment variables

```text
SACHIMA_ENABLED=<true-or-false>
SACHIMA_WEBHOOK_HOST=<listener-host>
SACHIMA_WEBHOOK_PORT=<listener-port>
SACHIMA_WEBHOOK_PATH=<listener-path>
SACHIMA_WEBHOOK_SECRET=<shared-hmac-secret>
SACHIMA_DELIVERY_URL=<external-client-callback-url>
SACHIMA_ALLOWED_USERS=<comma-separated-allowlist>
```

`SACHIMA_WEBHOOK_HOST` defaults to `127.0.0.1`, `SACHIMA_WEBHOOK_PORT` defaults to `8788`, and `SACHIMA_WEBHOOK_PATH` defaults to `/webhook/sachima`. Keep the listener on loopback by default and expose it through a separately approved external ingress design if an external IM platform or BFF must reach it.

`SACHIMA_DELIVERY_URL` is the long-term name for Sachima → external client delivery callbacks. The adapter prefers `SACHIMA_DELIVERY_URL` and falls back to the deprecated `SACHIMA_SEND_URL` alias during migration. Without a delivery URL, `SachimaAdapter.send()` stores canonical v1 delivery callback envelopes in `adapter.sent_messages`, which is useful for local tests and bridge development.

## Minimal inbound payload shape

POST to the configured webhook path. The default local path is `/webhook/sachima`; do not treat local examples as public exposure approval.

Canonical v1 payload:

```json
{
  "schema_version": "sachima.v1",
  "message_id": "msg-1",
  "chat_id": "chat-1",
  "user_id": "user-1",
  "role": "user",
  "text": "hello Hermes",
  "chat_type": "group",
  "thread_id": "thread-1",
  "reply_to_message_id": null,
  "attachments": [],
  "metadata": {}
}
```

Deprecated migration alias: `content` may be accepted only when `text` is absent, and is normalized to canonical `text` before dispatch.

Legacy/pre-v1 local payloads remain accepted for existing loopback tests:

```json
{
  "message_id": "msg-1",
  "text": "hello Hermes",
  "chat_id": "chat-1",
  "chat_name": "Sachima Lab",
  "chat_type": "group",
  "user_id": "user-1",
  "user_name": "狗哥",
  "thread_id": "thread-1"
}
```

Nested payloads are also supported:

```json
{
  "text": "hello group",
  "chat": {"id": "group-1", "name": "Group One", "type": "group"},
  "user": {"id": "user-2", "name": "Alice"},
  "message": {"id": "msg-2"},
  "thread_id": "thread-9"
}
```

Required v1 fields:

- `schema_version` — exactly `sachima.v1`
- `message_id`
- `chat_id`
- `user_id`
- `role` — exactly `user` for ingress
- `text` unless the payload contains at least one supported image attachment

Legacy local payloads without `schema_version` still use the historical required fields:

- `chat_id`
- `user_id`
- `text` unless the payload contains at least one supported image attachment

Optional fields:

- `message_id` / `id` / `message.id`
- `chat_name` / `chat.name`
- `chat_type` / `chat.type` — defaults to `dm`
- `user_name` / `user.name`
- `thread_id`
- `chat_topic`
- `reply_to_message_id`
- `reply_to_text`
- `attachments` — supported media attachments, currently images only
- `image_base64`, `image_url`, `image_mime_type`, `image_filename` — top-level image shortcut fields

## Inbound image payloads

Sachima image support normalizes incoming images into Hermes `MessageEvent.media_urls` local cache paths and `MessageEvent.media_types` MIME types. The resulting event uses `MessageType.PHOTO`. If an image payload has no text, the adapter uses `[Image]` as placeholder text so the message still enters Hermes safely.

Canonical base64 image attachment:

```json
{
  "message_id": "msg-img-1",
  "text": "帮我看看这张图",
  "chat_id": "chat-1",
  "user_id": "user-1",
  "attachments": [
    {
      "id": "att-1",
      "type": "image",
      "mime_type": "image/png",
      "filename": "photo.png",
      "base64": "iVBORw0KGgo..."
    }
  ]
}
```

Canonical URL image attachment:

```json
{
  "message_id": "msg-img-2",
  "text": "这张呢？",
  "chat_id": "chat-1",
  "user_id": "user-1",
  "attachments": [
    {
      "type": "image",
      "mime_type": "image/png",
      "url": "https://example.com/photo.png"
    }
  ]
}
```

Top-level shortcut shape:

```json
{
  "message_id": "msg-img-3",
  "chat_id": "chat-1",
  "user_id": "user-1",
  "image_base64": "iVBORw0KGgo...",
  "image_mime_type": "image/png",
  "image_filename": "photo.png"
}
```

Supported image MIME types:

- `image/png`
- `image/jpeg` / `image/jpg`
- `image/gif`
- `image/webp`
- `image/bmp`

Safety rules:

- Base64 attachments are checked against `extra.max_inbound_media_bytes` before decoding; default is 10 MiB decoded.
- URL attachments also use `extra.max_inbound_media_bytes`; the downloader rejects oversized `Content-Length` values and stops streaming once the byte cap is exceeded.
- If a single attachment contains both `base64`/`data` and `url`/`image_url`, Sachima treats the inline bytes as authoritative and skips the URL fetch to avoid duplicate media entries.
- Declared images still pass through image magic-byte validation before cache writes.
- Unsupported MIME types and non-image attachments are rejected for this phase.
- URL attachments use the shared Hermes SSRF-safe image downloader, blocking localhost/private/metadata-network targets.
- Attachment filenames never control cache paths; MIME determines a safe extension and the cache helper generates the filename.

## Configurable outbound text length

Long Sachima replies are split with `BasePlatformAdapter.truncate_message()` before sending. Default chunk size is 4000 characters; deployments can tune it in `config.yaml`:

```yaml
platforms:
  sachima:
    extra:
      max_message_length: 8000
      max_inbound_media_bytes: 10485760
```

Invalid `max_message_length` values (`0`, negative, non-integer, or too small) fall back to 4000.

## Webhook signing and idempotency

When `SACHIMA_WEBHOOK_SECRET` is set, requests must include:

```text
X-Sachima-Timestamp: <unix-seconds>
X-Sachima-Signature: <hex hmac sha256>
```

The signature base string is:

```text
<timestamp>.<raw-json-body-bytes>
```

and the signature is:

```text
hex(hmac_sha256(SACHIMA_WEBHOOK_SECRET, base_string))
```

Unsigned or invalid requests return `401` before entering Hermes session handling.

Webhook retries with the same `message_id` are deduplicated in memory. A duplicate request is acknowledged with:

```json
{"ok": true, "duplicate": true, "message_id": "msg-1"}
```

## Python smoke example

```python
from gateway.config import PlatformConfig
from gateway.platforms.sachima import SachimaAdapter

adapter = SachimaAdapter(PlatformConfig(enabled=True))
event = adapter.build_event_from_payload({
    "message_id": "msg-1",
    "text": "hello Hermes",
    "chat_id": "chat-1",
    "user_id": "user-1",
})
assert event.source.platform.value == "sachima"
```

## Sachima Envelope v1 delivery callback

`SachimaAdapter.send()` now emits canonical v1 delivery callback envelopes for both local fallback and configured callback URLs:

```json
{
  "schema_version": "sachima.v1",
  "message_id": "sachima-delivery-1",
  "chat_id": "chat-1",
  "user_id": "sachima-hermes",
  "role": "assistant",
  "text": "hello from Hermes",
  "reply_to_message_id": "msg-1",
  "metadata": {"thread_id": "thread-1"}
}
```

Configured HTTP callbacks use `SACHIMA_DELIVERY_URL` first and the deprecated `SACHIMA_SEND_URL` fallback only during migration. When `SACHIMA_WEBHOOK_SECRET` is configured, delivery callbacks include v1 HMAC headers over the exact transmitted JSON body.

A `2xx` response means the configured receiver accepted the HTTP callback. It does not prove browser-visible, user-visible, or real IM delivery.

## Phase B local fake-send simulator

Phase B adds a local-only fake `/send` simulator for delivery behavior proof before any PE-2 or live delivery work. It is test tooling, not a production adapter mutation.

Run the smoke evidence writer from a clean checkout:

```bash
python scripts/sachima_fake_send_simulator_smoke.py
```

The script starts a dynamic `127.0.0.1` fake `/send` endpoint, configures `SachimaAdapter.send()` directly with that loopback URL, sends synthetic `progress_card`, `rich_card`, `final_text`, `media`, and `artifact` surfaces, verifies duplicate idempotency, rejects an uninitialized delivery ref, and writes sanitized evidence to:

```text
outputs/sachima/phase-b-fake-send-simulator/phase_b_fake_send_simulator_evidence.json
```

Simulator transcript rows store safe delivery facts only: sequence, surface, fake message id, delivery ref, optional artifact ref, reply-to presence, content digest, bounded preview, ACK ref, and status. They must not store raw prompts, tool output, full cards, media bytes/paths, real platform IDs, credentials, callback payloads, or raw exceptions.

Boundary: this evidence may support a later PE-2 design packet request only. It does not approve PE-2 implementation, live/default-on behavior, real external Sachima ingress, production delivery control, production config writes, Gateway restart/reload, platform adapter mutation, or Gateway-owned Temporal lifecycle.

See `docs/runbooks/sachima-fake-send-simulator.md` for the full contract.

## Focused tests

Adapter/unit verification:

```bash
scripts/run_tests.sh tests/gateway/platforms/test_sachima.py tests/gateway/test_sachima_platform.py tests/gateway/test_sachima_fake_send_simulator.py tests/gateway/test_sachima_fake_send_surface_contract.py -q
```

Local adapter-only smoke test, no real LLM:

```bash
python scripts/sachima_smoke.py
```

Real GatewayRunner smoke test, using a temporary `HERMES_HOME`, adapter-owned webhook listener, fake Sachima send API, and the real Hermes agent/LLM:

```bash
python scripts/sachima_gateway_smoke.py
```

Expected successful real-gateway output includes:

```json
{
  "platforms": ["sachima"],
  "webhook_response": {
    "status": 200,
    "body": {"ok": true, "message_id": "real-gateway-msg-1"}
  },
  "received_sends": [
    {"text": "...home channel..."},
    {"text": "sachima-gateway-ok", "reply_to_message_id": "real-gateway-msg-1"}
  ],
  "matched": true
}
```

The optional home-channel notice is normal in the isolated temporary gateway home; the success criterion is the later `sachima-gateway-ok` delivery through the configured Sachima delivery callback URL.
