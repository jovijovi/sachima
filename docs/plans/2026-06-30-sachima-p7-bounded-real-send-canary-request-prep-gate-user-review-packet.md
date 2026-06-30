# P7 Bounded Real-Send Canary Request — Preparation Gate (User review packet)

Date: 2026-06-30
Owner: Architect
Status: Docs-only preparation packet. GitHub is the live authority for PR, head SHA, CI, and merge state.

## What this change does

Fixes the **canary request packet contract** for a future single bounded real send, while keeping the P7 controller default-off. It defines:

- the request packet schema — recipient safe label, surface allowlist, attempt and time budget, rollback control ref, evidence root, observability, no-leak;
- the acceptance/validation semantics — the explicit conditions under which a request **blocks execution**;
- the separated evidence model — execution-pipeline result vs user-visible business outcome;
- the binding of packet fields onto the existing controller policy plus the charter-level fields the policy does not hold;
- the separate, named send approval a real canary still requires, with every operator-supplied field marked required.

## What this change does not do

```text
no real bounded canary send (execution is a separate, later, named approval)
no concrete recipient / chat / user / group / message id / URL / token / credential / endpoint supplied or invented
no controller enablement and no use of the enable token
no real external ingress or delivery
no Gateway/Feishu/Lark/live/default-on behavior
no public ingress or webhook exposure
no production config write
no service restart/reload
no runtime/Worker/service/subprocess startup
no Gateway-owned Temporal/Worker lifecycle
no platform adapter mutation
no Sachima runtime acpx/npx/agent execution
no write-capable agent role
no production traffic
```

## Why this is the right next step

The P7 controller is implemented, default-off, and verified against a fake adapter seam; its boundary verdict is literally `..._ready_for_canary_request_only`. The honest next step is not to send — it is to fix *what a canary request must contain and must never contain* before anyone can responsibly grant a send approval.

Without this contract, a first real send could be waved through because it "looks small" while carrying a raw id, an unbounded surface set, an unbounded attempt count, no rollback handle, or an unsafe evidence root. This gate makes the request a reviewable, bounded object and stops one deliberate step short of execution.

## What a reviewer should check

- **Default-off preserved.** Nothing here enables the controller, uses the enable token, or performs a send. The change is docs/status only.
- **No invented recipient.** The recipient is a required operator-supplied safe label/class; no concrete raw id, URL, token, credential, or endpoint appears anywhere.
- **Block conditions are real gates.** Missing recipient label, any raw id/secret/private path, unbounded or out-of-set surfaces, `max_attempts` above the tiny canary ceiling (at or below 2), missing/unbounded time budget, missing rollback ref, evidence root outside an allowed class, or any out-of-canary surface each block execution with a stable reason — not a warning.
- **Packet binds to the real controller.** `recipient_safe_label` -> `approved_targets`, `surface_allowlist` -> `allowed_surfaces`, `delivery_url_class` -> `delivery_url_class`, `max_attempts` -> `max_attempts`; rollback maps to `controller.rollback()` (disable without Gateway restart).
- **Evidence is read correctly.** Execution-pipeline result and user-visible business outcome are separate; an accepted send is not delivery without a matching ACK closure; unknown/timeout is WATCH, never success.
- **Separation of approvals.** Implementation enable (control token) and bounded real-send canary (separate, not-yet-requested approval) stay distinct; the send approval template marks every concrete safe value as operator-required.

## Recommended next step after this gate

If this packet is accepted, the next request is **not** automatically a send. It is an operator-authored canary request that:

1. supplies a concrete safe recipient label/class (no raw id);
2. names `final_text` (or an explicitly approved tiny subset) as the only surface;
3. sets `max_attempts` at or below 2 and a bounded time-budget class;
4. names a rollback control ref that disables new sends without a Gateway restart;
5. names an evidence root within an allowed class;
6. carries the separate bounded real-send canary approval phrase with those concrete values bound to one execution packet.

Until such an approval exists with concrete safe values bound to one packet, P7 stays default-off and no real send occurs.

## Separate send approval phrase template

Operator fills every `<...>` slot; this gate supplies none and grants nothing:

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
