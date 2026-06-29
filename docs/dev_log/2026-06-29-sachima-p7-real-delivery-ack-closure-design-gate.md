# P7 Real Delivery / ACK Closure — Design Gate (Dev log)

Date: 2026-06-29
Owner: Architect
Branch: `docs/p7-real-delivery-ack-design`
Status: Docs-only design artifacts. GitHub is the live authority for PR, head SHA, CI, and merge state.

## Scope

Architect-owned, docs-only P7 design gate for real outbound delivery and ACK closure. No implementation, real ingress/delivery, Gateway/Feishu/Lark/live/default-on behavior, production config, service restart, runtime/Worker startup, platform adapter mutation, or Sachima runtime agent/acpx/npx execution.

## Authority read

- `GOAL.md`
- `docs/roadmap/current-status.md`
- `docs/sachima-channel.md`
- `docs/sachima-final-goal-gap-analysis.md`
- `docs/plans/2026-05-11-sachima-final-goal-phase-development-plan.md`
- `docs/plans/2026-05-12-flowweaver-pe2-design-packet.md`
- `docs/runbooks/flowweaver-delivery-activity-ack-reconciliation.md`
- `docs/runbooks/flowweaver-delivery-agent-execution-contract.md`
- `docs/runbooks/flowweaver-pe2-controlled-runtime-fake-delivery.md`
- `gateway/delivery.py`, `gateway/flowweaver_delivery_activity.py`, `gateway/flowweaver_pe2_controlled_runtime_delivery_bridge.py`

## Design conclusions

1. P7 must not treat fake-send evidence or an HTTP `2xx` callback as proof of real user-visible delivery.
2. Final text, rich cards, progress cards, media, and artifacts remain separate delivery slots.
3. ACKs derive from actual approved send outcomes or separately approved receipt events, never from planned slots.
4. Unknown delivery outcome becomes WATCH, not success.
5. Rollback disables new sends without requiring a Gateway restart.
6. Wire-level protocol authority remains in `sachima-protocols`; this repo records local implementation constraints only.

## Artifacts

- PRD: `docs/plans/2026-06-29-sachima-p7-real-delivery-ack-closure-design-gate-prd.md`
- Technical solution: `docs/plans/2026-06-29-sachima-p7-real-delivery-ack-closure-design-gate-technical-solution.md`
- Manifest: `docs/plans/2026-06-29-sachima-p7-real-delivery-ack-closure-design-gate-manifest.yaml`
- User review packet: `docs/plans/2026-06-29-sachima-p7-real-delivery-ack-closure-design-gate-user-review-packet.md`

## Why PR/CI facts are not frozen here

After push, GitHub is the authority for PR number/URL, head SHA, checks, mergeability, and merge state. This log deliberately omits those values so no later wording commit makes them stale. The current phase/task position lives in `docs/roadmap/current-status.md`.
