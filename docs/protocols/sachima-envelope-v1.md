# Sachima Envelope v1

Hermes' Sachima platform plugin implements the `sachima.v1` ingress and
delivery envelope. The canonical protocol specification is maintained in
[`jovijovi/sachima-protocols`](https://github.com/jovijovi/sachima-protocols/blob/main/protocols/envelope/v1.md).

Stable interoperability requirements:

- The signature input is `<unix-seconds>.<exact raw JSON body>` and the digest
  is hexadecimal HMAC-SHA256.
- `text` is canonical. `content` is accepted only as a migration alias when
  `text` is absent.
- Ingress envelopes use `role: user`; delivery envelopes use
  `role: assistant`.
- A successful HTTP callback means the receiver accepted the request. It does
  not prove that an end user saw the message.
- The adapter is disabled unless `platforms.sachima.enabled` is explicitly
  true, and production delivery additionally requires a callback URL.

Hermes accepts legacy unversioned payloads for migration, but emits canonical
`sachima.v1` delivery envelopes.
