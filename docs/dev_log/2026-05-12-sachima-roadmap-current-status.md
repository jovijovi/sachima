# Dev Log — Sachima Roadmap Current Status Dashboard

## Scope

User approved adding a long-task roadmap progress tracker to prevent goal drift.

Approved scope:

- add a reusable roadmap directory;
- add a living current-status dashboard for Sachima / FlowWeaver;
- update agent instructions so future agents read the status file before roadmap, phase, PR, CI, review, merge, or next-phase-readiness work;
- keep this as docs-only governance work.

Not approved:

```text
p4_implementation
real_external_sachima_ingress
real_external_delivery
production_delivery_control
production_config_write
gateway_restart_or_reload
platform_adapter_mutation
gateway_owned_temporal_lifecycle
production_agent_tool_execution_expansion
```

## Base / Worktree

```text
origin/feature/sachima-channel @ 1f587a0b0355f7eb18a2cdff64bc1bc93ea109dd
worktree: /home/ubuntu/workspace/hermes/worktrees/sachima/docs-roadmap-current-status
branch: docs/roadmap-current-status
```

Canonical checkout had local untracked files, so this docs work uses a clean workspace worktree.

## Design Decision

Create:

```text
docs/roadmap/README.md
docs/roadmap/current-status.md
```

Do not create `docs/phases/` and do not date-prefix the living status file.

Reason:

```text
GOAL.md = north star
canonical roadmap = planned route
docs/roadmap/current-status.md = current coordinate and drift guard
docs/dev_log/*.md = per-task ledger
outputs/ = evidence artifacts
```

The status file is intentionally thin. It links to canonical docs and evidence rather than copying whole plans or raw logs.

## Current Position Captured

```text
P1 PE-1D: done
P2 fake-send / simulator: done
P3 PE-2 design packet: done
Bridge PE-2A controlled runtime + fake delivery: done
P4 controlled external ingress: next, design packet only recommended
P5-P8: pending
```

Latest base captured:

```text
feature/sachima-channel @ 1f587a0b0355f7eb18a2cdff64bc1bc93ea109dd
PR #82: MERGED
```

## Agent Rule Captured

Future agents must read `docs/roadmap/current-status.md` before any roadmap/phase/PR/CI/merge/review/next-phase-readiness work and must not claim phase closure unless the status file is updated or marked N/A with reason.

## Verification Plan

- markdown/link/path sanity check;
- docs-only changed-file guard;
- forbidden approval drift scan;
- secret-shaped literal scan over changed files;
- independent docs/phase-gate review;
- PR + CI after local gates pass.

## Verification Log

```text
ROADMAP_STATUS_DOC_GATE_PASS
ROADMAP_STATUS_CHANGED_FILE_GATE_PASS
ROADMAP_STATUS_ADDED_LINES_NO_LEAK_GATE_PASS
ROADMAP_STATUS_NON_APPROVAL_GATE_PASS
git diff --check: PASS
```

A first whole-file secret-shaped scan hit pre-existing AGENTS.md baseline text, so the final no-leak gate scans added diff lines plus new files. This avoids false positives from old examples while still blocking newly introduced secret-shaped literals.

Independent docs / phase-gate review:

```text
VERDICT: PASS
BLOCKERS: None
```

Codex read-only blocker review:

```text
VERDICT: PASS
BLOCKERS:
- none
```

Reviewer summary: docs-only scope is preserved, P4 remains design-packet-only next, and explicit non-approvals remain clear for implementation, real ingress/delivery, Gateway restart/reload, production config writes, Temporal lifecycle, and production AI/tool execution.
