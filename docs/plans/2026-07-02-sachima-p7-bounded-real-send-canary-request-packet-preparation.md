# Sachima P7 — Bounded Real-Send Canary Request Packet Preparation

Date: 2026-07-02
Owner: Architect
Status: **Docs/status-only request-packet preparation.** This document *prepares* a
later, separately-approved one-execution P7 bounded real-send canary request. **It
does not itself authorize or perform execution.** It writes documentation and status
only. It adds no source or config, enables no controller, uses no enable token,
performs no real send, starts no Temporal Worker/service/runtime/subprocess,
constructs/mutates no platform adapter, runs no real agent/`acpx`/`npx`, touches no
Gateway/Feishu/live/default-on/public-ingress surface, writes no production config,
and enables no write-capable role. It supplies and invents **no** concrete recipient.

```text
Governance markers (in force for this gate)
P7_CANARY_REQUEST_PACKET_PREPARATION
P7_DOCS_ONLY_PREPARES_LATER_EXECUTION_APPROVAL
P7_DOES_NOT_AUTHORIZE_EXECUTION
P7_DEFAULT_OFF
P7_REAL_SEND_REQUIRES_SEPARATE_APPROVAL
P7_NO_CONCRETE_RECIPIENT_SUPPLIED_HERE
P7_LIVE_DEFAULT_ON_NOT_APPROVED
P7_PUBLIC_INGRESS_NOT_APPROVED
P7_PRODUCTION_CONFIG_WRITE_NOT_APPROVED
P7_GATEWAY_NOT_CALLER_NOT_LIFECYCLE_OWNER_NOT_WORKER_OWNER
P7_GATEWAY_RESTART_NOT_APPROVED
P7_TEMPORAL_WORKER_START_NOT_APPROVED
P7_REAL_AGENT_EXECUTION_NOT_APPROVED
P7_WRITE_ROLES_NOT_APPROVED
```

> **Naming boundary (read first).** This is the *P7 bounded real-send canary request
> **packet preparation*** gate. It assembles one bounded, safe-label-only request
> packet **shape** and its full pre-/post-execution gate set so that a single later
> named approval can bind it to exactly one execution. Preparing this package
> **enables nothing and sends nothing.** A real send remains a **separate, still-paused**
> gate — *P7 bounded real-send canary execute* (§9) — that requires a named approval
> phrase binding one concrete packet with operator-supplied safe values. Reading or
> merging this document does not grant that approval.

---

## 0. Verdict — what this preparation is, and is not

This package is a **prepared, reviewable request object plus its gate set**, not new
delivery capability and not an execution. The 2026-06-30 preparation gate fixed the
*contract* (the packet schema, block conditions, and pipeline-vs-business evidence
reading) before the S5 reconnect existed. This 2026-07-02 package does the next docs
step: now that the **S5 downstream delivery reconnect implementation** is a completed
project-task candidate (default-off, injected/fake send seam, S5-owned durable
pre-claim, no-double-send, receipt-only ACK, WATCH recovery), it **assembles a single
bounded canary request packet as concrete safe values (safe labels/classes only)**,
binds it to the now-real S5 reuse boundary and the merged P7 controller, and pins the
**pre-execution** and **post-execution** gates a later single execution must clear.

```text
merged, default-off delivery machinery (S5 reconnect + P7 controller: ready_for_canary_request_only)
  -> this package prepares ONE bounded canary request packet (safe labels only, execution_authorized=false)
  -> validated against block conditions (fail closed on first failure)  ->  eligible-for-send-approval | rejected(stable reason)
  -> a real send happens ONLY under a separate, named canary-execute approval binding this exact packet
  controller stays default-off until that approval exists
```

**This packet prepares a later execution approval and does not itself authorize
execution.** Passing every preparation gate here makes the packet *eligible to be
reviewed for* a send approval; eligibility is not execution.

### 0.1 Authority inputs

`GOAL.md`; `docs/roadmap/current-status.md`; the runbook
`docs/runbooks/sachima-p7-bounded-real-send-canary-request.md`; the 2026-06-30
preparation gate (`...-prep-gate-technical-solution.md`, `...-user-review-packet.md`,
`...-prep-gate-manifest.yaml`); the **S5 downstream delivery reconnect design packet**
(`docs/plans/2026-07-01-sachima-s5-downstream-delivery-reconnect-design-packet.md`) and
the **S5 implementation manifest**
(`docs/plans/2026-07-02-sachima-s5-downstream-delivery-reconnect-implementation-manifest.yaml`).
Temporal semantics referenced here are governed by **https://docs.temporal.io/ (source
of truth)**; any local `llm-wiki` synthesis is dated and non-authoritative. All explicit
non-approvals carried by those sources remain in force verbatim (§10).

---

## 1. Closed mapping — canary intent · channel · role · permission · target_ref · artifact_ref

*(Coverage item 1.)*

The prepared canary resolves along a **closed** mapping. Every element is either a
bounded enum, an operator-approved safe label, or a sanitized ref/digest. **None**
introduces a default surface, a permissive fallback, a caller-supplied policy override,
a platform-derived value, or a write-capable role. Each element fails closed **before**
any adapter call, with a stable P7 code and **zero** sends.

| Mapping element | Resolves from | Closed value in this packet (safe) | Fail-closed rule |
|---|---|---|---|
| **canary intent → surface** | S4 `artifact_kind` (a read-only report) + a caller-owned **PASS** over a verified artifact ref | one surface: `final_text` | non-`completed` output / caller BLOCK / unverified artifact → no slot built; unknown/unmapped kind or off-allowlist surface → `p7_delivery_surface_not_approved`. Surfaces are **independent**: a card/media surface never implies `final_text`. |
| **channel → target_ref** | operator-approved `policy.approved_targets` only | one `safe_<label>` (illustrative: `safe_p7_canary_target_01`) | a target not in `approved_targets`, or **any platform-derived recipient** → `p7_delivery_target_not_approved` / `p7_ack_unsafe_material`. A recipient class originates only from operator-approved policy, never from inbound platform material. |
| **role → delivery capability** | delivery policy (read-only report emission) | send of **one sanitized report artifact** only | any write / mutate / approve / reject delivery role, or an agent write role reused as a delivery role → fail closed. Delivery is a read-only report emission, not a state-mutating action. `WRITE_ROLES_NOT_APPROVED`. |
| **permission → admission** | default-off + exact enable token | `enabled=True` **and** exact `SACHIMA_P7_DELIVERY_ENABLE_TOKEN`, supplied **only at execution under the separate approval** | disabled (the default) → `p7_delivery_disabled`, zero adapter calls; any live/default-on/public-ingress assumption → fail closed. `LIVE_NOT_APPROVED`. |
| **target_ref** | `policy.approved_targets` (operator-bound at approval) | `safe_<label>` class only (see §2.1) | never a raw chat/user/group/message id, `@mention`, `oc_`/`ou_`/`om_` id, URL, or credential. |
| **artifact_ref** | S4 `ActivityOutput.artifact_ref` (`StepArtifactRef`) re-projected into the delivery namespace | `runtime_artifact_N` — refs + one `sha256:<64 hex>` digest only | bytes / raw material / oversized payload → rejected; never inlined; card JSON never built in the projection. |

The delivery idempotency key is `p7key_<safe suffix>`, derived deterministically from
the sanitized S4 refs plus surface — never from raw or platform material. Everything in
this mapping stays an opaque safe label/enum/ref through the whole path; a label is
bound to a concrete recipient and a concrete rendered card **only inside the future
Gateway adapter, under the separate real-send approval** (§6), never here.

---

## 2. Concrete safe values and the bounded execution shape

*(Coverage item 2.)*

The packet is prepared as `sachima.p7.bounded_canary_request_packet.v0`. Every value is
a **safe label, class, or bounded integer** — never a raw identifier, URL, secret, or
platform-derived value. The shape below is a single bounded execution: **one execution,
one target (safe label), one surface, default-off, no platform-derived values.**

| Bounded dimension | Prepared safe value | Explicit operator binding at approval time |
|---|---|---|
| executions | **exactly 1** (one bounded send) | the operator confirms single-execution in the approval phrase; this packet binds one attempt only. |
| surface | **single surface: `final_text`** | the operator must bind exactly `final_text`; any other surface or multi-surface set is out of packet scope and requires a new preparation gate before approval. |
| recipient (class) | `recipient_class = single_bounded_test_recipient` | the operator confirms the bounded recipient class; no platform id here. |
| recipient (label) | `recipient_safe_label = safe_p7_canary_target_01` — an **illustrative safe-label placeholder only** | the operator **binds the actual operator-approved target into `policy.approved_targets`** at approval time; this preparation supplies no recipient and resolves no label to any platform identity (§2.1). |
| delivery_url_class | `safe_p7_delivery_url_class_canary` — a **safe class label** accepted by the S5 policy validator, never a URL/secret | the operator confirms the class; the concrete endpoint lives only in the future adapter/config, never in this packet, state, log, or evidence. |
| max_attempts | **1** (single-send canary; stricter than the earlier ≤2 prep ceiling and the controller hard cap) | the operator binds this packet to one execution attempt; retry means a new named approval, not an automatic second send. |
| time_budget_class | `single_short_bounded_window` | the operator confirms a bounded observation-window class (a coarse class label, not a wall-clock secret). |
| rollback_control_ref | `controller.rollback` class — disable new sends, **no Gateway restart** | the operator confirms the disable-without-restart control ref. |
| evidence_root_ref | `p7_canary_evidence_root_class` — a safe evidence-root **class** within an allowed class | the operator confirms an allowed evidence class; the root holds sanitized counts/refs/codes only. |
| admission | **default-off**; `enabled=False` in preparation | the operator provides the exact enable token **only at execution under the separate approval**; disabled makes zero adapter calls. |
| execution_authorized | **`false`** in this preparation | the operator flips authorization **only** via the separate named approval bound to this exact packet (§9). |

### 2.1 The recipient is a safe label class — operator binding is explicit and required

`safe_p7_canary_target_01` is a **safe-label placeholder**, not a platform identifier
and not a supplied recipient. This package **does not** invent, supply, or resolve any
raw chat/user/group/message id, `@mention`, `oc_`/`ou_`/`om_` id, URL, endpoint, token,
or credential — and does not mention any private chat/user identity. The mapping from a
safe label to a real operator-approved target happens **only** inside `policy.approved_targets`,
bound by the operator **at approval time**, and the label is resolved to a real
recipient **only inside the future Gateway adapter under the separate real-send
approval**. Preparation pins the *shape and safe-label class*; it does not pin a
recipient.

---

## 3. S5 delivery / ACK reuse boundary — pre-claim · safe-receipt ACK · WATCH/ambiguous recovery · no-double-send

*(Coverage item 3.)*

The prepared canary reuses the **merged, default-off** S5 downstream delivery reconnect
implementation and the P7 delivery/ACK controller **unchanged**. It adds no new
delivery capability; it selects one bounded path through machinery that already exists
and is already default-off. The reuse boundary is the safety spine of any later
execution, so it is pinned here explicitly.

- **S5-owned durable pre-claim (before the adapter call).** A real send is irreversible,
  so idempotency is stricter than for a read-only step. The S5 reconnect writes a
  **durable delivery pre-claim keyed on the `p7key_...` idempotency key before it calls
  the P7 controller's `deliver_slot(...)`**, so the key is claimed before any adapter
  call can occur. A crash/restart after the pre-claim and before a terminal receipt
  recovers to the resident claim path and is **never** blindly re-sent. The merged P7
  controller keeps its own in-process/finalized projection after the adapter returns;
  S5 does not rely on that post-finalize record as the pre-send crash boundary.
- **ACK from a safe receipt only.** An ACK closure is recorded **only** from an accepted
  send response carrying a safe `receipt_ref`, or a separately-approved receipt event.
  It is **never** invented from an initialized slot, a planned delivery, a transcript
  row, a supervisor status, an exit code, or optimistic rendering. Raw platform callback
  payloads are denied as `p7_ack_unsafe_material` and scrubbed.
- **WATCH / ambiguous-outcome recovery.** An `accepted` pipeline result **with no
  matching receipt** is `p7_ack_missing` → **WATCH**, not delivered. A Temporal
  timeout, an `unknown` outcome, or a crash after the pre-claim before a terminal
  receipt reattaches to the resident claim/projection and resolves to **WATCH** — never
  to an optimistic success and never to a fabricated "not-sent". Pipeline result and
  business (ACK-closure) outcome are two axes, reported separately, never collapsed.
- **No-double-send.** A delivery maps to **exactly one adapter call per idempotency
  key**. An identical replay returns the resident delivery-state projection (no second
  send); a **divergent** replay (same key, different sanitized fingerprint) fails closed
  as `p7_divergent_replay` before any send; a distinct attempt against an already-acked
  slot is `p7_ack_duplicate`; attempts beyond the bound are `p7_max_attempts_exceeded`.
  Temporal retries are defense-in-depth **over** the S5 pre-claim and reconcile against
  resident state; they never perform a second send.

If a later execution could not honor this reuse boundary — a durable pre-claim with
cross-process no-double-send and WATCH-on-ambiguous behavior — it must **stop and
request a narrower named approval**, not proceed.

---

## 4. No-leak boundary — raw material stays out of history, query, log, status, and evidence

*(Coverage item 4.)*

The no-leak boundary is absolute and unchanged in strength. **raw prompt, raw context,
raw tool output, raw agent/`acpx` stdout/stderr, raw exception text/tracebacks, card
JSON, and platform identifiers do NOT enter Temporal history, query snapshots, heartbeat
details, the delivery-Activity result, the delivery-state projection, ACK events, this
status page, any export/evidence summary, or any log.** This package itself carries only
safe labels/classes and stable codes and adds no raw material.

- **Card JSON** is a raw platform payload: it is never built in the projection, never
  carried in the slot/attempt, and never written to history or the delivery-state
  projection. Only a sanitized `artifact_ref` + digest crosses; the card is rendered
  **inside the future Gateway adapter**, downstream of history.
- **Platform recipient identity** (a raw `chat_id`/`user_id`/`message_id`/`oc_`/`ou_`/
  `om_` id, `@mention`, or `feishu`/`lark` identifier) is never carried; the attempt
  holds only an operator-approved `safe_<label>` class.
- **Receipts** carry only a safe `receipt_ref`; raw callback payloads are denied and
  scrubbed.
- **Evidence and status** hold sanitized counts / refs / stable codes / digests only —
  never bytes, never raw material, never a platform id, never a secret.
- **Enforcement** is by construction (frozen, allowlist-only, schema-versioned
  projections; a no-throw delivery Activity that collapses raw exceptions to stable
  codes) **and** by scan (`scan_sachima_p7_no_leak(...)` over every projection/export,
  plus the JSON + serialized-bytes dual scan). A hit fails closed to
  `runtime_history_leak_detected` (upstream) / `p7_ack_unsafe_material` (downstream) and
  replaces the projection with a sanitized rejected marker carrying only a stable code.

---

## 5. Gateway boundary — not the Temporal caller, not the lifecycle owner, not the Worker owner

*(Coverage item 5.)*

For this preparation and for any later execution it prepares, the **Gateway is a
passive, injected leaf**, stated bluntly:

- **NOT the Temporal caller.** The controller that queries/recovers durable state and
  drives the delivery Activity is FlowWeaver/Hermes (caller-owned). The Gateway invokes
  nothing; it is a passive seam that gets called at most once per idempotency key.
- **NOT the lifecycle owner.** The Gateway owns no Workflow, Activity, Worker, task
  queue, namespace, or subprocess lifecycle. Worker/queue lifecycle is ops-owned. Per
  `GOAL.md` low-intrusion, the Gateway silently owns no Temporal service, Worker, task
  queue, daemon, socket, or subprocess.
- **NOT the Worker owner.** The Worker is ops-owned; the Gateway never owns, starts,
  restarts, or reloads it. Rollback disables delivery **without** a Gateway restart.

Nothing drives back up from the Gateway into Temporal. In this preparation the Gateway
surface is discussed as a **future** surface only; no platform adapter is constructed
and no network listener is opened. Any later execution uses an **injected send seam**,
and a **real** send is bound only by the separate real-send approval. `GATEWAY_NOT_APPROVED`.

---

## 6. Pre-execution gates — clear before a send approval is bound

*(Coverage item 6. Expressed as gate categories, not frozen commands or facts; a later
PR body or Hermes run carries the exact local command output and live GitHub/CI truth.)*

Before a canary-execute approval may be **bound to this exact packet**, all of the
following must hold. These are gate categories; this document records no PR number, head
SHA, CI result, or merge fact (those live in GitHub, the live authority).

1. **Packet validation.** The packet passes the block conditions of the 2026-06-30
   contract and the runbook — schema/known-field-set, forbidden-class scan (no raw id,
   URL secret, credential, bearer/token, signed-URL secret, or private path), bounded
   surface/attempt/time-budget, rollback presence, evidence-class check, scope scan, and
   `execution_authorized == false` — failing closed at the first failure with a stable
   reason. A passing packet is *eligible to be reviewed for* a send approval; eligibility
   is not execution.
2. **PR / CI.** The preparation change is opened as a PR and its CI is green before
   closeout. (The status dashboard does not record PR/head/CI/merge facts.)
3. **Codex read-only blocker review.** A read-only blocker review confirms no scope
   creep, no implied execution/enable/live/real-send approval, no leaked raw
   identifier/card JSON/recipient/secret/command, and that the closed mapping, bounded
   shape, S5 reuse boundary, no-leak boundary, and Gateway boundary preserve every
   existing boundary.
4. **Head-SHA-bound approval card.** The Feishu approval card is issued **bound to the
   latest head SHA**, so the approval attaches to the exact reviewed revision.
5. **Human approval bound to the exact packet.** A real send requires the separate,
   named canary-execute approval phrase (§9), with **every operator-supplied safe value
   filled** and bound to **one** concrete packet. Absent that approval with concrete
   safe values bound to one packet, P7 stays default-off and no real send occurs.

---

## 7. Post-execution gates — for the later single execution, if and only if separately approved

*(Coverage item 7. These govern the future single execution; this package performs
none of them and enables none of them. Evidence is sanitized counts / refs / stable
codes / digests only.)*

- **Single-send evidence.** Proof that **exactly one** adapter call occurred for the one
  `p7key_...` idempotency key. Reported on the `execution_pipeline_result` axis —
  adapter outcome (`accepted | failed | timeout | unknown`), an error-code histogram over
  the stable P7 codes, and retry/duplicate counts. An accepted send is **not** proof of
  delivery on its own.
- **ACK result.** Reported on the separate `user_visible_business_outcome` axis — an ACK
  closure recorded **only** from a safe `receipt_ref` (or an approved receipt event) for
  that exact slot. `accepted`-without-receipt → WATCH; `unknown`/`timeout` → WATCH, never
  success; a card/progress/media ACK never implies `final_text` delivery; the `final_text`
  slot resolves independently. The two axes are reported separately, never collapsed.
- **No-double-send evidence.** Proof that no second adapter call occurred under
  crash/retry/recover/cancellation: the S5 durable pre-claim reconciled resident state;
  an identical replay returned the resident projection; a divergent replay failed closed
  as `p7_divergent_replay`; a timeout/unknown resolved to WATCH rather than a re-send.
- **Rollback / stop conditions.** A single disable action (`controller.rollback()`)
  disables new sends (`p7_rollback_active`), preserves existing slot states and WATCH
  unknowns, keeps sanitized query/export available, and requires **no Gateway restart**.
  Stop conditions: fail closed on any divergent replay, any forbidden-class or leak hit,
  or any out-of-canary surface; WATCH (never optimistic success) on any unknown/timeout;
  and halt at the single-send ceiling (**1**).

---

## 8. Boundary discipline for this preparation

This gate is docs/status only and must remain so:

- no source, config, lockfile, runtime, or platform-adapter change; the merged S5
  reconnect module and `gateway/sachima_delivery_ack.py` are referenced **read-only**;
- no controller enablement, no enable-token use, no real send, no Worker/service/
  subprocess start, no Gateway restart/reload;
- no concrete recipient, raw id, URL, endpoint, token, credential, or secret supplied or
  invented; safe labels (e.g., `safe_p7_canary_target_01`) are labels only, never
  platform ids;
- no exact send/enable shell command frozen into these docs; the packet is a contract
  and a checklist, and live command output belongs to a later PR body or Hermes
  verification;
- `current-status.md` stays a lean dashboard, preserves every explicit non-approval, and
  records no PR/head/CI/merge fact.

---

## 9. This packet prepares a later execution approval — it does not authorize execution

The prepared packet becomes an execution **only** under a separate, named approval that
binds every `<...>` slot to concrete operator-supplied safe values against **one**
packet. This preparation supplies none of those values and grants nothing.

```text
approve_sachima_p7_bounded_real_send_canary_execute
  _recipient_safe_label_<operator_supplied_safe_label>
  _surface_allowlist_<final_text>
  _max_attempts_<1>
  _time_budget_<single_short_bounded_window>
  _rollback_control_ref_<disable_without_gateway_restart>
  _evidence_root_ref_<allowed_evidence_class>
  _single_bounded_send_no_live_default_on_no_public_ingress
  _no_production_config_write_no_gateway_restart_no_worker_lifecycle
  _no_real_agent_execution_no_write_roles_no_unbounded_delivery
```

Until that approval exists with concrete safe values bound to one packet, P7 stays
**default-off** and **no real send occurs.** The *P7 bounded real-send canary execute*
gate remains **paused**.

---

## 10. Explicit non-approvals (carried verbatim)

This preparation does **not** approve, and each remains a separate named gate:

```text
real external Sachima ingress
real external delivery / production delivery control
P7 real-send canary execute (paused; separate approval required)
Gateway / Feishu / live / default-on behavior
public webhook / ingress exposure
platform adapter construction or mutation
production config writes or service restart/reload
Gateway restart/reload
Gateway-owned Temporal / Worker / service / subprocess lifecycle
Temporal Worker / service / runtime / subprocess startup by this gate
real agent / acpx / npx execution, including any real read-only smoke
write-capable Claude/Codex roles or file/git/state/delivery mutation by agent steps
Satine or Hermes-profile ACP execution
production cluster or production traffic
```

---

## 11. Review / handoff

- **Architect (Claude Code):** owns this preparation document, its manifest, and the
  narrow `current-status.md` update that records it. The status update follows dashboard
  semantics — task-executor state only (`Done` / `In progress` / `Blocked` / `Not
  started` / `Paused`), no PR numbers, commit hashes, branch heads, CI/check matrices,
  merge status, or review histories. Docs only.
- **Codex CLI:** read-only blocker review — confirm no scope creep, no implied
  execution/enable/live/real-send approval, no leaked raw identifier/card JSON/recipient/
  secret/command, that the closed mapping / bounded shape / S5 reuse boundary / no-leak /
  Gateway boundary / pre-/post-execution gates preserve every existing boundary, that the
  Gateway stays a passive injected leaf performing no real send, that Temporal claims
  defer to https://docs.temporal.io/ , and that this gate grants only docs/status
  preparation.
- **Hermes:** controller / verifier / PR-approval closer — runs the docs/static checks
  (changed-file allowlist, stale-status wording scan, required non-approval markers,
  manifest/status parse, secret/no-leak/forbidden-approval-wording scan, `git diff
  --check`), opens the PR, drives CI green before closeout, and issues the Feishu
  approval card **bound to the latest head SHA**. No runtime, real send, delivery, or
  agent execution is part of this handoff.
