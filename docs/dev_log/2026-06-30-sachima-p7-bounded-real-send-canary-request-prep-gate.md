# P7 Bounded Real-Send Canary Request — Preparation Gate (Dev log)

Date: 2026-06-30
Owner: Architect
Branch: `docs/p7-bounded-canary-request-prep`
Status: Docs-only preparation artifacts. GitHub is the live authority for PR, head SHA, CI, and merge state.

## Scope

Architect-owned, docs-only preparation gate that fixes the contract for a future single bounded real-send canary **request**. No real send, controller enablement, enable-token use, real ingress/delivery, Gateway/Feishu/Lark/live/default-on behavior, public ingress, production config write, service restart, runtime/Worker/service/subprocess startup, platform adapter mutation, or Sachima runtime agent/acpx/npx execution. No concrete recipient is supplied.

## Authority read

- `GOAL.md`
- `docs/roadmap/current-status.md`
- `docs/plans/2026-06-29-sachima-p7-real-delivery-ack-closure-design-gate-prd.md`
- `docs/plans/2026-06-29-sachima-p7-real-delivery-ack-closure-design-gate-technical-solution.md`
- `docs/plans/2026-06-29-sachima-p7-real-delivery-ack-closure-design-gate-manifest.yaml`
- `docs/runbooks/sachima-real-delivery-ack-closure.md`
- `gateway/sachima_delivery_ack.py` (implementation reference only; not edited)

## Design conclusions

1. The P7 controller verdict is `..._ready_for_canary_request_only`; the honest next step is a bounded request contract, not a send.
2. A canary request is a reviewable, bounded object: recipient safe label, tiny surface allowlist (default `final_text`), tiny attempt ceiling (at or below 2), bounded time budget, rollback control ref, evidence root class, observability.
3. The recipient is operator-supplied as a safe label/class; raw chat/user/group/message ids, URL secrets, credentials, and private paths are forbidden in the packet, state, logs, and evidence.
4. Block conditions are hard gates, not warnings: a missing recipient label, any raw id/secret/private path, unbounded or out-of-set surfaces, an over-budget attempt count, a missing rollback ref, an out-of-class evidence root, or any out-of-canary surface each block execution.
5. Packet send-fields bind onto the existing controller policy (`approved_targets`, `allowed_surfaces`, `delivery_url_class`, `max_attempts`); time budget, rollback, evidence root, and observability are charter-level fields beside the policy.
6. Evidence is read on two separated axes: execution-pipeline result vs user-visible business outcome. An accepted send is not delivery without a matching ACK closure; unknown/timeout is WATCH, never success.
7. The implementation stays default-off. A real send remains a separate, not-yet-requested approval that must name concrete safe values and bind one execution packet.

## Artifacts

- PRD: `docs/plans/2026-06-30-sachima-p7-bounded-real-send-canary-request-prep-gate-prd.md`
- Technical solution: `docs/plans/2026-06-30-sachima-p7-bounded-real-send-canary-request-prep-gate-technical-solution.md`
- Manifest: `docs/plans/2026-06-30-sachima-p7-bounded-real-send-canary-request-prep-gate-manifest.yaml`
- User review packet: `docs/plans/2026-06-30-sachima-p7-bounded-real-send-canary-request-prep-gate-user-review-packet.md`
- Runbook: `docs/runbooks/sachima-p7-bounded-real-send-canary-request.md`
- Status: lean update to `docs/roadmap/current-status.md` reflecting the canary-request-prep slice, non-approvals preserved.

## Why PR/CI facts are not frozen here

After push, GitHub is the authority for PR number/URL, head SHA, checks, mergeability, and merge state. This log omits those values so no later wording commit makes them stale. The current phase/task position lives in `docs/roadmap/current-status.md`.
