# P7 Bounded Real-Send Canary Request — Preparation Gate (PRD)

Date: 2026-06-30
Owner: Architect
Status: **Default-off preparation gate.** This artifact fixes the contract for a *future* single bounded real-send canary **request**. It does not approve or perform a real send, does not supply a concrete recipient, does not enable the P7 controller, and does not authorize live/default-on behavior, public ingress, production config writes, Gateway/Feishu behavior, service/runtime/Worker/subprocess startup, or Sachima runtime agent/acpx/npx execution.
Branch: `docs/p7-bounded-canary-request-prep`
Base: `release/sachima`

## Scope

The P7 real delivery / ACK closure controller (`gateway/sachima_delivery_ack.py`) is implemented, default-off, and verified against a fake adapter seam. Its boundary verdict is explicitly `p7_delivery_ack_closure_implementation_ready_for_canary_request_only` — the implementation is ready for a canary **request**, not for a send.

This gate fixes the **canary request packet contract** that any later bounded real send must satisfy *before* a send approval can responsibly be granted. It:

1. defines the request packet schema — recipient safe label, surface allowlist, attempt and time budget, rollback path/class, evidence root, observability, no-leak, and the exact later approval binding;
2. fixes the acceptance/validation semantics — the explicit conditions under which a request packet **blocks execution**;
3. fixes how execution-pipeline result and user-visible business outcome are reported and interpreted separately;
4. keeps the implementation default-off and names the separate approval a real send still requires.

It is a paperwork gate that makes the eventual send small, bounded, and reviewable. It does not move the controller out of default-off.

## Authority inputs

- `GOAL.md` — production-grade IM AI workbench: safety before live capability, claim-check discipline, delivery separation, explicit named approvals.
- `docs/roadmap/current-status.md` — phase/feature dashboard and explicit non-approvals.
- `docs/plans/2026-06-29-sachima-p7-real-delivery-ack-closure-design-gate-prd.md` and `-technical-solution.md` — the design gate this prep gate builds on (FR6 real-send approval and target binding).
- `docs/runbooks/sachima-real-delivery-ack-closure.md` — the implemented default-off controller's operator runbook.
- `gateway/sachima_delivery_ack.py` — implementation reference only (policy/slot/attempt/ACK fields, stable error codes, no-leak scanner). Not edited by this gate.

## Position in the P7 line

```text
P7 design gate (2026-06-29)        -> fixed delivery-slot / ACK / retry / rollback / no-leak semantics
P7 implementation slice            -> default-off controller, fake adapter seam, verdict: ready_for_canary_request_only
P7 bounded canary request prep     <- THIS GATE: fix the request-packet contract + block conditions, still default-off
P7 bounded real-send canary        -> SEPARATE later approval, names concrete safe values, binds one execution packet
```

This gate is the controlled paperwork bridge between an implementation that is *ready to be asked* and a send that is *actually allowed*. It deliberately stops one step short of execution.

## Problem

The dangerous shortcut at this point is an unstructured "let's just send one real message to test it." Without a fixed request contract, a first real send could carry a raw chat/user/group id, an unbounded surface set, an unbounded attempt count, no rollback handle, or an evidence root outside a safe class — and could be waved through because it "looks small." Small is not the same as bounded.

The controller already fails closed on raw material and unapproved targets/surfaces at execution time. This gate moves that discipline **earlier**: it fixes, before any send approval, exactly what a canary request must contain, what it must never contain, and which conditions make it un-approvable. The request becomes a reviewable object, not an ad-hoc instruction.

## Non-goals / non-approvals

This preparation gate approves none of:

```text
a real bounded canary send (execution remains a separate, later, named approval)
supplying or inventing a concrete recipient, chat/user/group/message id, URL, token, credential, or endpoint
enabling the P7 controller or flipping its enable token
real external Sachima ingress
real external delivery or delivery-URL/config changes
Gateway/Feishu/Lark/live/default-on behavior
public ingress or webhook exposure
production config writes
service restart/reload
Gateway-owned Temporal/Worker/service/subprocess lifecycle
runtime/Worker/service/subprocess startup
platform adapter mutation
Sachima runtime agent/acpx/npx execution
write-capable agent roles
production cluster or production traffic
```

This document is docs/status only. It introduces no source, config, or runtime change. A concrete safe recipient label is **required from the operator before any send** and is intentionally **not** supplied here.

## The canary request packet contract

Design label only (no code added by this gate): `sachima.p7.bounded_canary_request_packet.v0`. A request packet is the operator-facing object a later send approval must carry. Its validated fields bind onto the existing controller policy (`approved_targets`, `allowed_surfaces`, `delivery_url_class`, `max_attempts`) plus charter-level fields the policy does not hold (time budget, rollback control ref, evidence root, observability).

```text
sachima.p7.bounded_canary_request_packet.v0
  request_meta
    type:                  sachima.p7.bounded_canary_request_packet.v0
    intent:                single_bounded_real_send_canary_request_prep
    default_off:           true
    execution_authorized:  false        # always false in this prep gate

  recipient
    recipient_safe_label:  REQUIRED, operator-supplied safe label   # binds to policy approved_targets + attempt target_ref
    recipient_class:       single_bounded_test_recipient | bounded_test_group
    raw_platform_id:       FORBIDDEN     # never a raw chat/user/group/message id

  surfaces
    surface_allowlist:     tiny allowlist; default {final_text} only unless a later approval widens it
    other_surfaces:        {progress_card, rich_card, media, artifact} OFF unless explicitly named and approved

  budget
    max_attempts:          tiny bounded integer (canary ceiling, see acceptance semantics) — stricter than the controller's hard cap
    time_budget_class:     single_short_bounded_window     # coarse class label, not a wall-clock secret

  rollback
    rollback_control_ref:  controller rollback() class — disable new sends, refuse with p7_rollback_active, preserve query/export, no Gateway restart
    stop_semantics:        a single stop/disable action must halt further sends without restarting Gateway/runtime/Worker

  evidence
    evidence_root_ref:     safe evidence-root class label within an allowed class   # sanitized counts/refs/codes only
    evidence_class:        sanitized_counts_refs_codes_only

  observability
    counters:              per surface and status; retry/duplicate counts; stable error-code histogram; rollback proof; no-leak scan result
    pipeline_vs_business:  execution-pipeline result and user-visible business outcome reported as separate fields

  no_leak
    forbidden_markers:     raw_prompt, card_json, media_path, media_bytes, callback_payload, chat_id, user_id,
                           message_id, recipient_id, credential, token, secret, bearer, Traceback,
                           private home/temp paths, signed-URL query secrets

  approval_binding
    implementation_enable_token_ref:  SACHIMA_P7_DELIVERY_ENABLE_TOKEN   # control token; enables the controller, NOT the send
    canary_send_approval_phrase:      REQUIRED separate approval; names concrete recipient_safe_label, surface_allowlist,
                                      max_attempts, time_budget_class, rollback_control_ref, evidence_root_ref
```

The recipient is represented only by a safe label/class. Concrete raw identifiers are forbidden in the packet, in durable state, in logs, and in evidence. The packet binds a single execution; it is not a standing send permit.

## Acceptance / validation semantics

A request packet is **rejected and blocks execution** when any of the following holds. Each maps to a stable, sanitized reason; none is a soft warning.

```text
recipient_safe_label missing or empty                         -> block  (no concrete safe recipient => no send)
any raw chat/user/group/message id, URL secret, credential,
  bearer/token, signed-URL secret, or private filesystem path -> block  (claim-check violation)
surface_allowlist empty, unbounded, or outside the tiny set   -> block  (final_text-only default unless approval widens)
max_attempts absent, non-integer, or above the canary ceiling -> block  (canary must stay tiny; ceiling stricter than controller cap)
time_budget_class absent or unbounded                         -> block
rollback_control_ref absent or not a disable-without-restart  -> block  (no rollback handle => no send)
evidence_root_ref outside an allowed evidence class           -> block
any named Gateway/Feishu/live/default-on/public-ingress/
  production-config/service-lifecycle/Worker/subprocess/
  agent/acpx/npx/write-role surface                           -> block  (out of canary scope)
execution_authorized != false within this prep gate           -> block  (this gate never authorizes a send)
```

The canary attempt ceiling is intentionally tiny: a bounded real-send canary exists to observe one path once, with at most a single bounded retry. A request asking for more than that is, by definition, no longer a canary and must be re-scoped under its own approval. The exact ceiling value is set by the operator's canary approval and must be **at or below 2**; the controller's own hard cap (a larger maximum) is a backstop, not the canary budget.

A packet that passes validation is *eligible to be reviewed for a send approval*. Passing validation is **not** itself a send approval.

## Observability & evidence interpretation

Evidence from a future canary must be read with two separated axes:

1. **Execution-pipeline result** — what the adapter seam returned: `accepted`, `failed`, `timeout`, or `unknown`, plus the stable error-code histogram and retry/duplicate counts.
2. **User-visible business outcome** — whether the human recipient actually received the final text, recorded only via a matching ACK closure (`ack` from a `send_response` receipt ref or an approved receipt event).

Interpretation rules:

```text
an accepted send is NOT proof of final delivery unless a matching ACK closure is recorded for that exact slot
a card / progress / media ACK never implies final_text delivery (final_text is its own slot)
unknown or timeout outcome is WATCH, never success
divergent duplicate replay fails closed before any second send
all counters, refs, and codes are sanitized; no raw payload or private id may appear in any evidence surface
```

A canary that returns `accepted` with no matching ACK is a WATCH result to investigate, not a green light.

## Prep-gate completion criteria

This preparation gate is complete when:

- the request packet schema, the block conditions, and the pipeline-vs-business interpretation are each specified unambiguously enough to validate a future request against;
- no concrete recipient, raw id, URL, token, credential, or endpoint is invented anywhere in the artifacts;
- the implementation stays default-off, and the change is docs/status only with no source/config/runtime surface touched;
- the separate later send approval is named with its required operator-supplied fields;
- `current-status.md` reflects this prep slice while preserving every explicit non-approval.

## Required later approvals (kept separate)

Two distinct gates remain, in order, and neither is granted here:

1. **Implementation enable** — flipping the controller to enabled requires the exact control token `SACHIMA_P7_DELIVERY_ENABLE_TOKEN`. This enables the controller against an adapter seam; it does **not** by itself authorize a real send.
2. **Bounded real-send canary** — a separate approval, not yet requested, that must name concrete safe values and bind exactly one execution packet. Proposed phrase template (operator fills every `<...>` slot; this gate supplies none):

```text
approve_sachima_p7_bounded_real_send_canary_execute
  _recipient_safe_label_<operator_supplied_safe_label>
  _surface_allowlist_<final_text_or_named_subset>
  _max_attempts_<integer_at_or_below_2>
  _time_budget_<single_short_bounded_window>
  _rollback_control_ref_<disable_without_gateway_restart>
  _evidence_root_ref_<allowed_evidence_class>
  _single_bounded_send_no_live_default_on_no_public_ingress
  _no_production_config_write_no_gateway_restart_no_worker_lifecycle
  _no_real_agent_execution_no_write_roles_no_unbounded_delivery
```

Until that approval exists with concrete safe values bound to one packet, P7 stays default-off and no real send occurs.
