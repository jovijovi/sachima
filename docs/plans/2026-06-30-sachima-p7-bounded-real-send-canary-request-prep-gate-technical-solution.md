# P7 Bounded Real-Send Canary Request — Preparation Gate (Technical solution)

Date: 2026-06-30
Owner: Architect
Status: **Docs-only, no-code technical solution.** No source, config, or runtime change. No real send, controller enablement, live/default-on behavior, public ingress, production config write, service restart, Worker/runtime/subprocess startup, platform adapter mutation, or Sachima runtime agent/acpx/npx execution is approved here.

## 0. Verdict

The canary request packet is **a validation contract over already-existing controller semantics, not new delivery capability.** This gate adds no code. It specifies how a future operator request is shaped, validated, and bound so that — *if and only if* a separate send approval is later granted — exactly one bounded real send can be executed and read correctly.

```text
canary request packet (operator-authored, later)
  validated against block conditions  ->  eligible-for-send-approval | rejected(stable reason)
  on a separate send approval only     ->  binds onto P7 controller policy + one execution attempt
  controller stays default-off until that approval exists
```

## 1. Field binding: packet -> controller policy

The packet's send-relevant fields bind onto the implemented controller policy from `gateway/sachima_delivery_ack.py`. Charter-level fields (time budget, rollback control, evidence root, observability) sit beside the policy because the controller policy does not carry them.

| Packet field | Binds to | Controller behavior already enforced |
|---|---|---|
| `recipient_safe_label` | `policy.approved_targets` + attempt `target_ref` | Target not in `approved_targets` => `p7_delivery_target_not_approved` before any adapter call. |
| `surface_allowlist` | `policy.allowed_surfaces` | Surface not in allowlist => `p7_delivery_surface_not_approved`; surfaces are independent slots. |
| `delivery_url_class` | `policy.delivery_url_class` | Empty class => `p7_delivery_url_unconfigured`; class label only, never a URL/secret. |
| `max_attempts` (canary ceiling) | `policy.max_attempts` | Attempts beyond the bound => `p7_max_attempts_exceeded`. Canary ceiling is stricter than the controller's hard cap. |
| `rollback_control_ref` | `controller.rollback()` | Disables new sends (`p7_rollback_active`), preserves query/export, requires no Gateway restart. |
| `time_budget_class` | charter only | Bounds the observation window; coarse class label, not a wall-clock secret. |
| `evidence_root_ref` | charter only | Names a sanitized evidence root within an allowed class. |
| `observability` | charter + `scan_sachima_p7_no_leak` | Separates pipeline result from business outcome; no-leak scan over every projection. |

The packet does **not** introduce a second policy type or a parallel send path. It is the human-reviewable request whose accepted values are copied into the existing policy at the (separate, later) moment of a granted send approval.

## 2. Validation algorithm (design, not code)

A future validator — owned by a later send-approval step, not by this gate — must apply these checks in order and **fail closed** at the first failure. Each failure yields a stable, sanitized reason; none degrades to a warning.

```text
1. shape:      packet is a plain mapping with the known field set; reject unknown/extra side-effect fields
2. recipient:  recipient_safe_label present, non-empty, label-shaped; recipient_class in the bounded set
3. no-raw-id:  no raw chat/user/group/message id, URL secret, credential, bearer/token, signed-URL secret, or private path anywhere
4. surfaces:   surface_allowlist non-empty, within the tiny set, default {final_text}; no surface outside it
5. budget:     max_attempts integer and <= canary ceiling (<= 2); time_budget_class present and bounded
6. rollback:   rollback_control_ref present and is a disable-without-Gateway-restart control
7. evidence:   evidence_root_ref present and within an allowed evidence class
8. scope:      no Gateway/Feishu/live/default-on/public-ingress/prod-config/service-lifecycle/Worker/subprocess/agent/acpx/npx/write-role surface named
9. authority:  execution_authorized is false in this prep gate; a send needs the separate canary approval phrase
=> pass: eligible-for-send-approval (NOT a send approval)
=> any failure: rejected(stable_reason), no eligibility
```

The validator is a paperwork guard that runs before any controller call. Even a fully valid packet only becomes *eligible to be reviewed* for a send approval; eligibility is not execution.

## 3. Verifier categories

Verification of this gate and of any future request packet is expressed as categories, not frozen commands (a later PR body or Hermes run can carry exact local command output):

- **schema validation** — the packet parses as the known field set with no extra/side-effect fields;
- **forbidden-class scan** — no raw id, URL secret, credential, bearer/token, or private path is present;
- **bound checks** — surface allowlist is tiny and defaulted to `final_text`; `max_attempts` is within the canary ceiling; time budget is bounded;
- **rollback presence** — a disable-without-restart control ref exists;
- **evidence-class check** — the evidence root is within an allowed class;
- **no-leak scan** — `scan_sachima_p7_no_leak(...)` reports zero forbidden markers over every projection, log line, and evidence summary;
- **scope scan** — no out-of-canary surface (Gateway/Feishu/live/default-on/public-ingress/prod-config/service-lifecycle/Worker/subprocess/agent/acpx/npx/write-role) is named.

## 4. Observability / evidence model

Two axes, reported separately, never collapsed:

```text
execution_pipeline_result
  adapter outcome:   accepted | failed | timeout | unknown
  error-code histogram over the stable P7 codes
  retry / duplicate counts

user_visible_business_outcome
  ack closure:       ack recorded only from a send_response receipt ref or an approved receipt event
  final_text slot resolved independently of any card/progress/media slot
  unknown / timeout  -> WATCH, never success
```

Reading rule: an `accepted` pipeline result with no matching ACK closure is a WATCH outcome, not a delivered outcome. Evidence is sanitized counts / refs / codes only.

## 5. Boundary discipline

This gate is docs/status only and must remain so:

- no source, config, lockfile, runtime, or platform-adapter change;
- no controller enablement, no enable-token use, no real send;
- no exact send command frozen into design docs; the request packet is a contract and a checklist, and live command output belongs to a later PR body or Hermes verification, not to these artifacts;
- the implemented controller is referenced read-only; `gateway/sachima_delivery_ack.py` is not edited;
- any future static scope scan is an execution-time guardrail, not a substitute for this contract.

A later send PR (if and only if a canary approval is granted) defines its own concrete verification, binds exactly one packet with concrete operator-supplied safe values, and carries its own evidence. This gate does not pre-authorize that PR.

## 6. Review handoff

This prep gate is successful only if:

- the request packet schema, block conditions, and pipeline-vs-business interpretation are each specified unambiguously;
- no concrete recipient, raw id, URL, token, credential, or endpoint appears anywhere;
- the controller stays default-off and no source/config/runtime file is modified;
- `current-status.md` remains a lean dashboard and preserves every explicit non-approval;
- the bounded real-send canary remains a distinct, named approval that still must supply concrete safe values and bind one execution packet.
