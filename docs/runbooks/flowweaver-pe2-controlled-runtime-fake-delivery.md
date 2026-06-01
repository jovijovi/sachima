# FlowWeaver PE-2A Controlled Runtime + Fake Delivery Runbook

## Status

```text
PE2A_CONTROLLED_RUNTIME_FAKE_DELIVERY_IMPLEMENTATION
PE2A_LOOPBACK_OR_SYNTHETIC_ONLY
PE2A_REAL_EXTERNAL_INGRESS_NOT_APPROVED
PE2A_REAL_DELIVERY_NOT_APPROVED
PE2A_GATEWAY_RESTART_NOT_APPROVED
PE2A_PRODUCTION_CONFIG_WRITE_NOT_APPROVED
PE2A_GATEWAY_OWNED_RUNTIME_LIFECYCLE_NOT_APPROVED
```

## Scope

PE-2A connects:

```text
sanitized Sachima ingress envelope
-> caller-supplied runtime control surface
-> Phase B fake-send simulator
-> runtime delivery ACK recording
-> sanitized local evidence
```

It does **not** connect public ingress, real IM delivery, production config, Gateway restart/reload, Gateway-owned Temporal lifecycle, or production agent/tool execution.

## Start / Smoke

Run from a clean PE-2A worktree:

```bash
source .venv/bin/activate 2>/dev/null || source venv/bin/activate 2>/dev/null || source "$HOME/.hermes/hermes-agent/venv/bin/activate"
PE2A_BASE_SHA=$(git rev-parse --short=12 HEAD) python scripts/flowweaver_pe2_controlled_runtime_fake_delivery_smoke.py
```

Expected markers:

```text
PE2A_CONTROLLED_RUNTIME_FAKE_DELIVERY_EVIDENCE_PASS
PE2A_FINAL_GATE_PASS
```

Evidence path:

```text
outputs/sachima/pe2a-controlled-runtime-fake-delivery/pe2a_controlled_runtime_fake_delivery_evidence.json
```

Runtime evidence is local verification material. Do not commit `outputs/` unless a later approval explicitly says so.

## Disable / Rollback Probes

The smoke covers these fail-closed cases:

- `enabled=false` policy returns `disabled` and makes zero runtime/fake-send calls.
- missing fake-send surface returns `fake_send_surface_required` before runtime calls.
- uninitialized delivery ref returns `fake_send_rejected` and records zero runtime ACKs.
- duplicate ingress discriminator returns duplicate without a second runtime/fake-send chain.
- restore after disabled policy can run one fresh controlled chain.

Git rollback is ordinary revert of these implementation files; no production config or service rollback is needed because PE-2A owns no live lifecycle.

## No-Leak Invariants

Evidence, result objects, fake transcript rows, and runtime requests may contain only:

- synthetic labels;
- runtime refs;
- ACK refs;
- counts;
- stable statuses/error codes;
- booleans;
- sanitized surface names.

They must not contain raw request bodies, raw user text, platform IDs, callback payloads, card payloads, media paths/bytes, tool output, credentials, signatures, raw exception text, or full agent results.

## Next Gate

The strongest PE-2A outcome is:

```text
pe2a_evidence_ready_for_external_ingress_design_request_only
```

That allows requesting a future external-ingress design packet. It does not approve live/default-on behavior, real delivery, production runtime lifecycle, production config writes, or Gateway restart.
