# Sachima R5 Controlled Canary / Product Hardening Runbook

This runbook is for local/offline R5 evidence only. It does not authorize real-send execution, platform delivery, live ingress, production config mutation, Gateway lifecycle work, Temporal Worker/service startup, real AGENT execution, or write-capable roles.

## Operator intent

Use R5 to prove that a bounded canary packet can be represented safely before any later execution gate exists.

The runtime spine core may retain:

- an opaque `safe_*` target ref;
- an opaque `safe_*` receiver-bridge ref;
- `final_text` as the exact surface;
- `max_attempts: 1`;
- refs for artifact, evidence, rollback, and dry-run report.

The runtime spine core must not retain:

- concrete receiver address book entries;
- platform identifiers;
- delivery URLs;
- raw prompts, context, tool output, agent stdout, raw exception text, card JSON, or private paths;
- any result that claims a real send occurred.

## Local/offline acceptance

1. Build a `CanaryRequestPacket` using safe refs only.
2. Validate the packet is default-off, dry-run-only, and execution-not-authorized.
3. Build a `CanaryDryRunReport` from the packet.
4. Confirm report counters have `send_attempts == 0` and `sent == 0`.
5. Confirm serialization is deterministic and no-leak safe.
6. Confirm any forged send success, receiver mapping exposure, widened surface, or widened attempt count fails closed.

## Stop conditions

Stop the R5 path and request a narrower approval if continuing requires any of:

- concrete receiver mapping in core artifacts;
- real send or delivery;
- platform adapter mutation;
- Gateway/service lifecycle action;
- production config write;
- Temporal Worker/service/runtime startup;
- real agent/acpx/npx execution;
- write-capable role.

## Later execution boundary

A future bounded real-send approval must name one exact safe target, one exact surface, one exact attempt budget, one receiver class, one evidence class, and one rollback/stop policy. The R5 packet is preparation evidence only; it is not execution approval.
