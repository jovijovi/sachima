# Sachima Protocols

This directory contains canonical wire-protocol documents for Sachima-controlled external integrations.

## Canonical documents

- `sachima-envelope-v1.md` — canonical Sachima Envelope v1 wire contract for controlled external ingress and delivery callbacks.

## Ownership rule

Sachima owns external wire protocols because it is the Gateway/channel boundary. Client projects, including agentic-ui, may keep adaptation notes in their own repositories, but those notes must cite this directory instead of redefining the canonical protocol.

## Versioning rule

Protocol files are stable, non-dated documents. Version changes should be additive when possible and must state migration behavior, compatibility aliases, required probes, and explicit non-approvals.
