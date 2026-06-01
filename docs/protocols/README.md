# Sachima Protocols

This directory contains local pointers and legacy notes for Sachima-controlled external integration protocols. Current normative protocol text lives in the dedicated `jovijovi/sachima-protocols` repository.

## Canonical documents

- `sachima-envelope-v1.md` — local pointer to the canonical Sachima Envelope v1 wire contract at `https://github.com/jovijovi/sachima-protocols/blob/main/protocols/envelope/v1.md`.

## Ownership rule

Sachima owns external wire protocols because it is the Gateway/channel boundary. Current normative specs live in `jovijovi/sachima-protocols`; client projects, including agentic-ui, may keep adaptation notes in their own repositories, but those notes must cite the protocol repository instead of redefining the canonical protocol.

## Versioning rule

Protocol files are stable, non-dated documents. Version changes should be additive when possible and must state migration behavior, compatibility aliases, required probes, and explicit non-approvals.
