# Roadmap Status Tracking

This directory contains living roadmap status documents for long-running, multi-phase work.

## Files

- `current-status.md` — the living progress dashboard for this repository.

## Relationship to other project documents

```text
GOAL.md = final goal, north-star principles, and durable product direction
canonical roadmap = planned route, phase definitions, gates, and rubrics
current-status.md = current position, evidence links, tails, and next allowed request
docs/dev_log/*.md = per-task execution ledger
outputs/ = runtime evidence artifacts, not PR payload unless explicitly approved
```

`current-status.md` is not a replacement for the canonical roadmap. It is a compact index that tells an agent where the project is right now and what is still blocked.

## Agent preflight rule

Before any roadmap, phase-gate, PR, CI, merge, review, or next-phase-readiness work, agents must read `current-status.md` and the canonical roadmap linked from it.

Before changing files, the agent must identify:

- the current phase position;
- the next allowed request;
- explicit non-approvals;
- open `BLOCKER`, `NEXT_PHASE`, `WATCH`, or `PARKED` tails;
- whether the requested task is allowed by the current status.

If `current-status.md` is missing, stale, or contradicts the requested work, stop and report the drift risk before making changes.

## Update rule

Update `current-status.md` when any of these happens:

- a master phase closes;
- a bridge phase closes;
- a phase PR merges;
- a next-phase readiness decision changes;
- a tail item is added, closed, or reclassified;
- a new non-approval or approval boundary is established.

A roadmap/phase task is not complete until `current-status.md` reflects the new phase state, or the PR explains why the status update is not applicable.
