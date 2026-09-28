# Sachima channel

Sachima is a bundled, default-off gateway platform plugin for a custom IM
channel. It supports direct messages, groups, threads, replies, signed webhook
ingress, callback delivery, retry deduplication, text chunking, and image
attachments.

## Configuration

Behavior belongs in the active profile's `~/.hermes/config.yaml`:

```yaml
platforms:
  sachima:
    enabled: true
    extra:
      delivery_url: https://im.example.test/hermes/callback
      webhook_host: 127.0.0.1
      webhook_port: 8788
      webhook_path: /webhook/sachima
      allowed_users: [user-1, user-2]
      max_message_length: 4000
      max_inbound_media_bytes: 10485760
```

Credentials remain in the same profile's `.env`:

```dotenv
SACHIMA_WEBHOOK_SECRET=<shared-hmac-secret>
SACHIMA_API_KEY=<optional-callback-bearer-token>
```

`delivery_url` is required for normal operation. The deprecated `send_url`
key remains accepted during migration. `extra.local_mode: true` enables the
in-memory delivery recorder used by tests and local bridge development; it is
never an implicit fallback when delivery is unconfigured.

The listener defaults to `127.0.0.1:8788` at `/webhook/sachima`. Public
exposure, reverse proxy configuration, and gateway startup are operator-owned
actions and are not performed by enabling the plugin code.

## Ingress envelope

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

Required v1 fields are `schema_version`, `message_id`, `chat_id`, `user_id`,
`role`, and either non-empty `text` or a supported image. The role must be
`user`. Legacy unversioned flat and nested payloads remain accepted for
migration.

When `SACHIMA_WEBHOOK_SECRET` is configured, ingress requests need:

```text
X-Sachima-Timestamp: <unix-seconds>
X-Sachima-Signature: <hex-hmac-sha256>
```

The signed bytes are `<timestamp>.<raw-body>`. Repeated `message_id` values are
acknowledged as duplicates without dispatching a second Hermes turn.

## Images

Canonical attachments may contain either base64 image bytes or an HTTPS URL:

```json
{
  "type": "image",
  "mime_type": "image/png",
  "filename": "photo.png",
  "base64": "iVBORw0KGgo..."
}
```

Supported MIME types are PNG, JPEG, GIF, WebP, and BMP. Inline content is
bounded by Sachima's `max_inbound_media_bytes`; downloaded content uses the
shared `gateway.max_inbound_media_bytes` limit. Both paths check valid image
magic and use Hermes' generated cache names. URL inputs use the shared
SSRF-safe downloader. If inline bytes and a URL are both present, inline bytes
are authoritative and the URL is not fetched.

## Delivery

Replies are emitted as `sachima.v1` assistant envelopes to `delivery_url`.
The plugin preserves `reply_to_message_id` and thread metadata, splits long
text according to `max_message_length`, signs callbacks when a webhook secret
is configured, and adds the optional bearer credential when configured.

Run the scoped offline contract suite with:

```bash
scripts/run_tests.sh tests/plugins/platforms/test_sachima.py
```
