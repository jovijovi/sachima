# Sachima P7 Bounded Real-Send Canary Request Runbook

## Status

```text
P7_BOUNDED_CANARY_REQUEST_PREPARATION
P7_DEFAULT_OFF
P7_CONTROLLER_NOT_ENABLED_BY_THIS_RUNBOOK
P7_REAL_SEND_REQUIRES_SEPARATE_APPROVAL
P7_NO_CONCRETE_RECIPIENT_SUPPLIED_HERE
P7_LIVE_DEFAULT_ON_NOT_APPROVED
P7_PUBLIC_INGRESS_NOT_APPROVED
P7_PRODUCTION_CONFIG_WRITE_NOT_APPROVED
P7_GATEWAY_RESTART_NOT_APPROVED
P7_GATEWAY_OWNED_WORKER_LIFECYCLE_NOT_APPROVED
```

## Scope

This runbook is the operator workflow for **assembling and validating a bounded
real-send canary request packet** before requesting a send approval. It does not
enable the controller and does not send. The implemented controller
(`gateway/sachima_delivery_ack.py`) stays default-off until a separate canary
approval names concrete safe values and binds one execution packet.

```text
implemented default-off controller (verdict: ready_for_canary_request_only)
-> operator assembles a bounded canary request packet (safe labels only)
-> packet validated against block conditions (fail closed on first failure)
-> eligible-for-send-approval | rejected(stable reason)
-> a real send happens only under a separate, named canary approval
```

## Request packet (safe labels only)

`sachima.p7.bounded_canary_request_packet.v0`. Every value is a safe label,
class, or bounded integer. Raw identifiers and secrets are forbidden.

```text
recipient_safe_label:  REQUIRED operator-supplied safe label    # binds to policy approved_targets + attempt target_ref
recipient_class:       single_bounded_test_recipient | bounded_test_group
surface_allowlist:     {final_text} only, unless a later approval widens it
delivery_url_class:    safe class label, never a URL or secret
max_attempts:          tiny canary ceiling, at or below 2       # stricter than the controller's hard cap
time_budget_class:     single_short_bounded_window
rollback_control_ref:  controller.rollback() class — disable new sends, no Gateway restart
evidence_root_ref:     safe evidence-root class label within an allowed class
observability:         per-surface/status counters; retry/duplicate counts; error-code histogram; rollback proof; no-leak result
```

The recipient is named only by label/class. A concrete raw chat/user/group/
message id is **never** placed in the packet, state, logs, or evidence. This
runbook does not supply a recipient; the operator must.

## Acceptance / block conditions

Validate in order and fail closed at the first failure. Each failure yields a
stable, sanitized reason; none is a soft warning.

```text
recipient_safe_label missing or empty                          -> BLOCK
any raw chat/user/group/message id, URL secret, credential,
  bearer/token, signed-URL secret, or private filesystem path  -> BLOCK
surface_allowlist empty, unbounded, or outside the tiny set    -> BLOCK
max_attempts absent, non-integer, or above the canary ceiling  -> BLOCK
time_budget_class absent or unbounded                          -> BLOCK
rollback_control_ref absent or requires a Gateway restart      -> BLOCK
evidence_root_ref outside an allowed evidence class            -> BLOCK
any Gateway/Feishu/live/default-on/public-ingress/prod-config/
  service-lifecycle/Worker/subprocess/agent/acpx/npx/write-role
  surface named                                                -> BLOCK
execution_authorized not false in preparation                  -> BLOCK
```

A packet that passes is *eligible to be reviewed for a send approval*. Passing
validation is not a send approval.

## Verifier categories

Expressed as categories, not frozen commands; a later PR body or Hermes run
carries exact local command output:

- **schema validation** — packet is the known field set with no extra/side-effect fields;
- **forbidden-class scan** — no raw id, URL secret, credential, bearer/token, or private path;
- **bound checks** — tiny surface allowlist defaulted to `final_text`; `max_attempts` within the canary ceiling; bounded time budget;
- **rollback presence** — a disable-without-restart control ref exists;
- **evidence-class check** — evidence root within an allowed class;
- **no-leak scan** — `scan_sachima_p7_no_leak(...)` reports zero forbidden markers over every projection, log line, and evidence summary;
- **scope scan** — no out-of-canary surface is named.

## Evidence interpretation

Two axes, reported separately, never collapsed:

```text
execution_pipeline_result        adapter outcome accepted | failed | timeout | unknown; error-code histogram; retry/duplicate counts
user_visible_business_outcome    ACK closure recorded only from a send_response receipt ref or an approved receipt event
```

- an accepted send is **not** proof of delivery without a matching ACK closure for that exact slot;
- a card/progress/media ACK never implies `final_text` delivery;
- unknown / timeout is WATCH, never success;
- divergent duplicate replay fails closed before any second send.

## Rollback expectation for a future send

A future canary, if approved, must keep a single disable action that:

```text
1. disables P7 delivery admission;
2. refuses new sends with p7_rollback_active;
3. preserves existing slot states and WATCH unknowns;
4. keeps sanitized query/export available;
5. requires no Gateway restart.
```

## Separate send approval (not granted here)

A real bounded canary send needs a separate approval phrase with every `<...>`
slot filled by the operator with concrete safe values, bound to one packet:

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

Until that approval exists with concrete safe values bound to one packet, P7
stays default-off and no real send occurs.
