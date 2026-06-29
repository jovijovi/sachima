# Sachima Roadmap Current Status

> Lean project dashboard. This file records the current project phase, feature/task implementation status, active blockers, and next allowed work. It is not a GitHub/PR log.

## How to read this file

- GitHub is the authority for PRs, commits, CI, and merge history.
- `current-status.md` is the authority for the current project dashboard only: phase, feature/task state, blockers, boundaries, and next decision.
- Historical PR ledgers, tail registers, and evidence indexes are not routine status surfaces for this project.
- External evidence is referenced only when it materially supports a current stage decision and is not already represented by GitHub/CI/PR metadata.

## Current project position

| Field | Current truth |
|---|---|
| Product goal | Production-grade AI workbench inside a custom IM channel, with safe durable FlowWeaver/Hermes orchestration and controlled delivery surfaces. |
| Current phase | P7 — real delivery / ACK closure design gate. |
| Current implementation focus | Docs-only P7 design gate for real delivery / ACK closure; no real delivery, live/default-on behavior, or implementation is approved by this status. |
| Current repo state | `release/sachima` is the integration branch; GitHub/open-PR state is reflected only in the generated machine block below. |
| Not yet started | P7 source implementation, bounded real-send canary, limited live pilot, and P8 product/ops hardening. |

## Stage / feature board

| Stage / feature | Status | Meaning | Next |
|---|---|---|---|
| P5 Temporal Slice 1 | Done | Default-off caller-owned Temporal Slice 1 with controlled-deterministic step body. | Use only as prerequisite evidence for later runtime work; no production traffic implied. |
| P6-A controlled AI FLOW composition | Done | Default-off outer P6 composition over WP4 + P5 seam; deterministic/injected-fake step bodies only. | No real agent execution or live delivery implied. |
| P6-B bounded read-only real-agent step | Done for the single approved smoke | One pinned local `acpx@0.10.0` / Codex read-only one-shot PASS was recorded; no duplicate replay/recover and no live surfaces. | Any additional real agent/acpx/npx execution requires separate approval. |
| P6 runtime lifecycle / controlled attach | Done as implementation slice | Adds a default-off caller-owned attach shell over an already supplied P6 session, with fail-closed admission, sanitized state, idempotency, no-relaunch recovery, and WP3b WATCH preservation. | If more runtime lifecycle work is needed, start a new narrow gate; do not treat this as Worker/runtime startup approval. |
| Feishu task workbench title summary | Done | Task-card title summary stabilization is merged. | No phase change. |
| Feishu PR approval-card stale-head hardening | Done | Reissuing a PR approval card invalidates older unresolved same-PR cards and fails closed on stale callbacks/resolvers. | Runtime deployment/restart is operational, not a roadmap phase. |
| P7 real delivery / ACK closure | Design gate in progress | Docs-only design is being prepared to define slot lifecycle, ACK source-of-truth, retry/duplicate/WATCH behavior, rollback, and no-leak rules. | If merged, request separate default-off implementation approval; real send/canary/live rollout remain separate gates. |
| P8 product / ops hardening | Not started | Product/ops hardening after limited live-pilot readiness. | Requires P7/live-pilot readiness first. |

## Active blockers / gates

| Gate | Status | Required before |
|---|---|---|
| Additional real agent/acpx/npx execution | Not approved | Any new real agent run, real smoke beyond the recorded one-shot, or broader controlled AI FLOW real execution. |
| Write-capable Claude/Codex roles | Not approved | Any role that can modify files or perform non-read-only agent execution through Sachima. |
| Gateway/Feishu/live/default-on behavior | Not approved by roadmap status | Any live IM behavior, automatic delivery, platform adapter mutation, public ingress, or default-on route. |
| Production config / service lifecycle | Not approved by roadmap status | Production config writes, Gateway-owned Temporal/Worker lifecycle, runtime/Worker/service/subprocess startup, or production traffic. |
| WP3b active-run cancellation | WATCH | Any claim that active host/ACP runs can be reliably interrupted mid-run. |

## Next allowed work

The next safe mainline request should be one of:

1. **P6 status/implementation follow-up** — only if a concrete runtime lifecycle gap is found, still default-off and local/offline unless separately approved.
2. **P7 implementation gate** — only after the P7 design gate is merged and a separate implementation approval is given; keep default-off and avoid real sends.
3. **Docs/status hygiene** — keep this dashboard lean and aligned with live repo truth without recreating PR ledgers or tail registers.

## Explicit non-approvals

This status page does **not** approve:

- real external Sachima ingress;
- real external delivery or production delivery control;
- Gateway/Feishu/live/default-on behavior;
- public webhook exposure;
- production config writes or service restarts;
- Gateway-owned Temporal/Worker/service/subprocess lifecycle;
- additional real acpx/npx/agent execution beyond the recorded approved bounded smoke;
- write-capable Claude/Codex roles;
- Satine or Hermes-profile ACP execution;
- production cluster or production traffic.

## Completion rule

A roadmap/phase task is complete only when:

- the feature/task row above reflects its current implementation status;
- blockers and non-approvals remain explicit;
- GitHub/CI/PR facts are left to GitHub instead of copied here as a ledger;
- any non-GitHub evidence is referenced only when it materially affects the current decision.

## Machine-owned dynamic status

<!-- sachima-status-sync:start -->
> Generated by `tools/sync_roadmap_status.py`; do not edit manually.
> Source of truth: git/GitHub. This block is evidence only; it does not grant approvals.

```json
{
  "base_branch": "release/sachima",
  "base_head": "ac26c0448c197b9de1dbde8e084db236c78b4389",
  "base_head_note": "latest first-parent base commit excluding machine status-sync self-commits",
  "open_pr_count": 0,
  "open_prs": [],
  "repository": "jovijovi/sachima",
  "scope_note": "machine dynamic status only; GitHub remains the authority for PR/merge/CI history, and approvals/phase meaning remain human-authored outside this block"
}
```
<!-- sachima-status-sync:end -->
