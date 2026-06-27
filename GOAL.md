# Sachima Project Goal

## One-sentence goal

Sachima should become a production-grade AI workbench inside a custom IM channel: a safe, reliable, durable, observable, and recoverable Hermes/FlowWeaver system designed for real production use, able to receive real IM requests, orchestrate long AI workflows, deliver results back through the channel, and preserve clear operational control.

## Target architecture

```text
Sachima = custom IM entrypoint and product surface
FlowWeaver = long-task transaction / intent / operation / artifact / delivery state machine
Hermes Agent = reasoning and tool execution engine
Hermes Gateway = platform rendering, delivery, and ACK boundary
Temporal / durable runtime = recoverable execution, retry, query, update, audit, and rollback backbone
```

## Final product behavior

The final Sachima experience should let an operator use IM as a real AI workbench:

1. Send a natural-language request, text or supported media, through Sachima.
2. Have Hermes classify and split the request into high-density intent summaries, never raw-text fallback cards.
3. Start a durable FlowWeaver transaction with sanitized state only.
4. Show progress, approvals, blockers, artifacts, and delivery state in the IM surface.
5. Run long AI FLOW tasks such as planning, coding, testing, PR creation, CI wait, merge coordination, report generation, and recovery.
6. Deliver final text, rich cards, media, and artifacts without suppressing or confusing delivery surfaces.
7. Survive process restarts, retries, duplicate messages, partial failures, and operator rollback.
8. Keep raw prompts, platform IDs, card JSON, media bytes/paths, tool output, credentials, and raw exception text out of durable history and user-visible evidence.

## Non-negotiable principles

- Safety before live capability: prove no-leak, fail-closed, and rollback before enabling wider behavior.
- Low intrusion: Gateway should not silently own Temporal service, Worker, task queue, daemon, Docker, socket, or subprocess lifecycle.
- Explicit approvals: production config writes, Gateway restart/reload, real external ingress, delivery control, platform adapter mutation, PE-2 implementation, and live/default-on behavior each require separately named approval.
- Exact scoping: Sachima PE-1 allowlist remains exact `[sachima]`; duplicates, extra platforms, hostile list/string subclasses, and forged policies fail closed.
- Claim-check discipline: durable state carries sanitized refs, counts, digests, statuses, and stable error codes, not raw material.
- Delivery separation: final text, rich cards, progress cards, media, and ACKs are tracked as separate surfaces.

## Current phase line

Current stable state after PE-1D / PE-2 readiness decision:

```text
PE-1 controlled Sachima shadow observation: proven locally and rollback-tested.
PE-1D longer controlled local observation: eligible for separate approval.
PE-2 design packet: eligible for separate approval.
PE-2 implementation / live / default-on: NO-GO.
```

## Planning basis

Use these documents as the canonical project compass:

- `GOAL.md` — this project goal and boundary summary.
- `docs/sachima-final-goal-gap-analysis.md` — detailed gap analysis and phase-planning basis.
- `docs/plans/2026-05-11-flowweaver-pe1d-pe2-readiness-decision-packet.md` — latest readiness decision and explicit non-approvals.
- `docs/sachima-channel.md` — current Sachima adapter/channel behavior.
