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

## Environment variables

```bash
SACHIMA_ENABLED=true
SACHIMA_WEBHOOK_HOST=127.0.0.1
SACHIMA_WEBHOOK_PORT=8788
SACHIMA_WEBHOOK_PATH=/webhook/sachima
SACHIMA_WEBHOOK_SECRET=[REDACTED]
SACHIMA_SEND_URL=http://127.0.0.1:9000/send
SACHIMA_ALLOWED_USERS=dog,cat
# Optional open-access development flag:
# SACHIMA_ALLOW_ALL_USERS=true
```

`SACHIMA_WEBHOOK_HOST` defaults to `127.0.0.1`, `SACHIMA_WEBHOOK_PORT` defaults to `8788`, and `SACHIMA_WEBHOOK_PATH` defaults to `/webhook/sachima`. Keep the listener on loopback by default and expose it through a reverse proxy if an external IM platform must reach it.

`SACHIMA_SEND_URL` is optional. Without it, `SachimaAdapter.send()` stores outbound messages in `adapter.sent_messages`, which is useful for local tests and bridge development.

## Minimal inbound payload shape

POST JSON to the configured webhook path, default:

```text
POST http://127.0.0.1:8788/webhook/sachima
```

Flat payload:

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

Required fields:

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

## Outbound send API expectation

When `SACHIMA_SEND_URL` is configured, the adapter posts JSON like:

```json
{
  "chat_id": "chat-1",
  "content": "hello from Hermes",
  "reply_to": "msg-1",
  "metadata": {"thread_id": "thread-1"}
}
```

If `PlatformConfig.api_key` or `extra.api_key` is set, the request includes:

```text
Authorization: Bearer <api-key>
```

A `2xx` response is treated as success. Non-`2xx` responses become failed `SendResult`s; `429` and `5xx` responses are marked retryable.

## Focused tests

Adapter/unit verification:

```bash
pytest tests/gateway/test_sachima_platform.py tests/gateway/platforms/test_sachima.py -q
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
    {"content": "...home channel..."},
    {"content": "sachima-gateway-ok", "reply_to": "real-gateway-msg-1"}
  ],
  "matched": true
}
```

The optional home-channel notice is normal in the isolated temporary gateway home; the success criterion is the later `sachima-gateway-ok` delivery through `SACHIMA_SEND_URL`.
