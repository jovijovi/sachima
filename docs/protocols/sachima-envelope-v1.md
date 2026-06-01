# Sachima Envelope v1

> Local pointer for the canonical external Sachima wire protocol.
>
> The normative protocol text now lives in `jovijovi/sachima-protocols`:
> <https://github.com/jovijovi/sachima-protocols/blob/main/protocols/envelope/v1.md>

## Canonical authority

The canonical Sachima Envelope v1 specification is now maintained in the dedicated protocol repository:

```text
repo: jovijovi/sachima-protocols
spec: protocols/envelope/v1.md
url: https://github.com/jovijovi/sachima-protocols/blob/main/protocols/envelope/v1.md
```

This file remains in the Sachima product repository only as a roadmap/preflight pointer so existing agents and phase-gate readers know where the live protocol text moved.

## Stable v1 reminders

Sachima Envelope v1 still defines the controlled external ingress and delivery callback contract:

- HMAC timestamps use Unix seconds.
- HMAC verification signs `{timestamp}.{raw_body}` and must use the exact raw request body.
- `text` is canonical.
- `content` is a deprecated migration alias only.
- `SACHIMA_DELIVERY_URL` is the long-term delivery callback URL name.
- Delivery callback HTTP `2xx` means callback accepted by receiver only; it does not prove browser-visible, IM-visible, or user-visible delivery.
- Client repositories such as agentic-ui are conformance targets, not protocol authority.

## Non-approval boundary

Moving the protocol text into `jovijovi/sachima-protocols` does **not** approve any implementation or runtime behavior.

Still not approved:

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

For current roadmap state, open tails, and the next allowed request, read `docs/roadmap/current-status.md` before making changes.
