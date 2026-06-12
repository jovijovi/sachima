# agent-run-supervisor × Sachima Phase E — Persistent Sessions & Cancellation Design Packet

> **For Hermes:** This is a **docs-only design packet**. Do not implement runtime code, do not run any local execution, session, or cancellation, and do not start any service, Worker, CLI, Docker container, socket, Gateway, Feishu/IM surface, or `acpx`/`npx` process from this document. It does **not** approve implementation, persistent session execution, cancellation execution, real local `exec`, real AGENT execution, controlled AI FLOW execution, live/default-on behavior, Gateway involvement, Feishu/IM delivery, real external ingress, production config writes, or real delivery. A later, separately named approval is required before any of those.

**Goal:** Define the persistent-session and cancellation **semantics** for the supervisor → Sachima mainline, on top of the merged durable-runtime ownership design (PR #102), the durable-state preflight (PR #107), the Phase C controlled one-shot exec wrapper (PR #114), the Phase D smoke readiness/prerequisites gates (PR #117/#119), and the single passed Phase D read-only real local smoke. PR #102 deliberately deferred the lifecycle labels `session_open`, `session_turn`, `session_closed`, `cancel_requested`, `cancelled`, and `rolled_back` as NOT approved in that phase; this packet gives those labels full design semantics. It still approves **no execution of any kind**.

**Architecture:** Sachima/FlowWeaver (the caller) owns durable product/transaction/session state and every business decision, exactly as decided in PR #102. `agent-run-supervisor` remains an independent local supervision library that owns local run/session internals and redacted evidence **only once invoked by an approved caller**. The Gateway is excluded as caller, lifecycle owner, renderer, and delivery surface. Feishu/IM is excluded entirely.

---

## Status Markers

```text
DESIGN_ONLY
IMPLEMENTATION_NOT_APPROVED
PERSISTENT_SESSION_EXECUTION_NOT_APPROVED
CANCELLATION_EXECUTION_NOT_APPROVED
REAL_AGENT_EXECUTION_NOT_APPROVED
CONTROLLED_AI_FLOW_EXECUTION_NOT_APPROVED
NO_LIVE
NO_GATEWAY
NO_FEISHU
NO_REAL_DELIVERY
NO_PRODUCTION_CONFIG
```

Scoped markers (for grep / dashboard use):

```text
ARS_SACHIMA_PHASE_E_PERSISTENT_SESSIONS_CANCELLATION_DESIGN_ONLY
ARS_SACHIMA_PHASE_E_PERSISTENT_SESSION_EXECUTION_NOT_APPROVED
ARS_SACHIMA_PHASE_E_CANCELLATION_EXECUTION_NOT_APPROVED
ARS_SACHIMA_PHASE_E_REAL_AGENT_EXECUTION_NOT_APPROVED
ARS_SACHIMA_PHASE_E_CONTROLLED_AI_FLOW_EXECUTION_NOT_APPROVED
ARS_SACHIMA_PHASE_E_LIVE_NOT_APPROVED
ARS_SACHIMA_PHASE_E_GATEWAY_NOT_APPROVED
ARS_SACHIMA_PHASE_E_FEISHU_NOT_APPROVED
ARS_SACHIMA_PHASE_E_REAL_DELIVERY_NOT_APPROVED
ARS_SACHIMA_PHASE_E_PRODUCTION_CONFIG_NOT_APPROVED
```

Strongest allowed outcome of this PR:

```text
phase_e_persistent_sessions_cancellation_design_open_for_merge_decision
```

That means: a Phase E persistent-sessions/cancellation **design packet exists and may be reviewed/merged**. It does not authorize implementation, persistent session execution, cancellation execution, real AGENT execution, controlled AI FLOW execution, live/default-on behavior, Gateway/Feishu involvement, production config writes, or real delivery.

## Approval and Boundary

User approval received in chat (verbatim):

```text
批准准备 Phase E persistent sessions / cancellation docs-only design gate，仍遵循 AGENT 分工，不批准 live/Gateway/Feishu/生产/真实投递。
```

Interpretation:

- **Approved:** preparing a Phase E persistent sessions / cancellation **docs-only design gate**, following the established AGENT split.
- **Not approved:** live behavior, Gateway involvement, Feishu/IM involvement, production config/surfaces, real delivery — and, by the standing roadmap non-approvals, implementation of any kind, persistent session execution, cancellation execution, additional real AGENT execution, `acpx`/`npx` invocation, and controlled AI FLOW execution.

AGENT split for this gate:

```text
Hermes      = PM / controller / verifier / repo operator / evidence arbiter (runs gates, commits, opens PR)
Claude Code = architect + documentation engineer (this packet; docs only; no commit/push/PR/merge/runtime)
Codex CLI   = primary blocker reviewer after the draft
```

The author (Claude Code) does not commit, push, open PRs, merge, restart services, write production config, invoke `acpx`/AGENT processes, or touch Gateway/Feishu/live surfaces.

## Goal Trace

```text
Goal: Sachima becomes Dog Brother's safe, durable, observable, recoverable IM AI workbench that can run long AI FLOW
      tasks and deliver sanitized results, surviving restarts, retries, duplicates, partial failures, and rollback.
Gap:  The mainline has proven exactly one bounded local read-only one-shot exec (Phase C wrapper PR #114 + Phase D
      smoke PASS). Long AI FLOW tasks need multi-turn persistent sessions and a safe way to stop work in flight.
      Today nothing defines WHO may open/hold/close a local session, HOW turns bind to leases and open-state checks,
      WHAT a cancellation request is (vs cancellation execution), or HOW ambiguous session/turn state must fail
      closed. Without that design, a later implementation could double-launch agents, leak session internals into
      durable state, double-close or orphan local processes, or drift into unapproved execution.
Phase: Phase E — docs-only persistent sessions / cancellation design gate, positioned after the Phase D smoke PASS
       and before any persistent-session or cancellation implementation request.
Task: Define the persistent session model (records, lifecycle, leases/epochs/session binding, command semantics),
      the cancellation model (request vs execution, operator gate, idempotency, terminal/ambiguous states),
      concurrency rules (lease-internal open-state recheck, lifecycle guard, lock ordering, fail-closed ambiguity),
      no-leak durable-state/log rules, a stable failure taxonomy extension, future implementation gates with a
      precise recommendation, and the docs-only verification gates for this PR.
Test: Docs marker gate, manifest YAML parse, status sync, changed-file allowlist (4 docs/status paths), no source
      diff, secret/no-leak scan, forbidden-surface scan, optional pytest/compileall on the unchanged
      sachima_supervisor suite if Hermes chooses, CodeGraph status, and Codex primary blocker review.
Evidence: This packet + manifest + dev log + current-status update; merged evidence of PR #102/#107/#114/#117/#119;
      Phase D smoke manifest/dev log and out-of-repo evidence; factual code references (sachima_supervisor/
      local_offline.py mode allowlist, activity_controlled_exec.py claim/CAS + role capability gate,
      activity_preflight.py, supervisor_library.py exact pin).
Decision: If this design merges, the next safe request is a separate LOCAL/OFFLINE persistent-session lifecycle
      preflight / state-machine implementation gate (injected fakes only, no real session launch, no cancellation
      execution). Persistent session execution, cancellation execution, real AGENT execution, controlled AI FLOW,
      live/Gateway/Feishu/production config/real delivery remain blocked behind separate approvals.
```

## Level Selection

**Level 3 — High Risk design (docs-only).**

Persistent sessions and cancellation are **runtime lifecycle semantics**: they govern long-lived local processes, multi-step durable state transitions, leases and lock ordering, interruption of in-flight work, and cleanup guarantees. Ambiguity here later becomes double-launched agents, orphaned local processes, double-close signals, durable-state leakage of session internals, or silent drift into unapproved execution. The packet therefore gets the same Level 3 discipline as the PR #102 durable-runtime design: strict markers, manifest, explicit non-approvals, no-leak rules, stable failure taxonomy, and independent Codex blocker review.

## Current Baseline and Evidence

| Evidence | Current state | Design impact |
|---|---|---|
| `GOAL.md` | Safety before live capability; low intrusion; explicit per-axis approvals; claim-check discipline; delivery separation. | Sessions/cancellation must be designed fail-closed and caller-owned before any execution approval can even be requested. |
| PR #102 — durable runtime ownership & controlled local execution design (merge `e49709d6e960b8e11f8e220fa087488132f64f93`) | Defines records/leases/attempts/query projections/state transitions; explicitly defers `session_open`, `session_turn`, `session_closed`, `cancel_requested`, `cancelled`, `rolled_back` as NOT approved in that phase. | Phase E adopts exactly those deferred labels and gives them design semantics; ownership decision is inherited unchanged. |
| PR #107 — durable-state preflight implementation (merge `6795da2930324cde1448586e71ff8d80bc6e9ae1`) | Fail-closed local/offline preflight validating approval/mode/role/evidence-digest/lease/state-version/idempotency/operator-gate/budget preconditions; sanitized projections only; no supervisor/runtime call. | The session preflight/state-machine slice recommended below is the session-shaped extension of this proven pattern. |
| PR #114 — Phase C controlled local exec first slice (merge `21d1bafc22c6fcde2bb0af6fff6becfb0886cf4f`) | Default-off `exec_controlled` **one-shot** wrapper: pinned-local-acpx no-fetch provenance, role-file sha256 binding, atomic pre-launch claim/CAS under a single in-process mutex, claim-outside-launch-finalize discipline, sanitized claim projections, `business_verdict` permanently null. Role capability gate **fails closed on any persistent session strategy** (`session.strategy != "exec"` rejected). | Sessions reuse the claim/CAS + provenance + capability-gate discipline; a session-capable role config is a NEW, separately allowlisted design label — no existing runnable role can open a session. |
| PR #117 / PR #119 — Phase D readiness + smoke prerequisites (merges `eb7227301d715b40d4eb6628bf32fb800017bd42`, `0c9e4342e2befe1db6ecf5774c51b313c8bb5f5b`) | Pinned local acpx provenance verifier, deterministic prompt materialization seam (Phase C default `prompt=None`), `agent_run_supervisor` exact-pin checker (`supervisor_library.py`, expected version exactly `0.0.0`). | Pinned local acpx + exactly pinned supervisor library are hard prerequisites for any future session implementation; prompt materialization stays a separately gated seam for session turns too. |
| Phase D real local smoke (manifest `docs/plans/2026-06-12-agent-run-supervisor-sachima-phase-d-real-local-smoke-manifest.yaml`; dev log `docs/dev_log/2026-06-12-agent-run-supervisor-sachima-phase-d-real-local-smoke.md`) | Exactly one host-local read-only Codex one-shot through pinned local acpx 0.10.0: execution pipeline PASS, business verdict PASS, replay created no extra run, no leftover acpx/codex processes, evidence outside the repo. | Proves the one-shot baseline sessions build on; the no-leftover-process and replay-no-duplicate checks generalize into session cleanup and idempotency requirements. |
| `sachima_supervisor/local_offline.py` (factual reference only) | Seam `SUPPORTED_MODES` already reserves `session_create`, `session_send`, `session_status`, `session_close`; cancellation/rollback are deliberately absent from the seam allowlist. | Session command labels already exist at the seam but nothing above the seam may use them; cancellation execution would require NEW supervisor-side support that does not exist today. |
| `sachima_supervisor/activity_controlled_exec.py`, `activity_preflight.py` (factual reference only) | Claim store statuses `claimed_in_progress | completed | failed_retryable | failed_terminal`; validate-on-read projections; preflight lease/epoch/state-version binding. | Session/turn/cancellation records below generalize these proven shapes; no code is changed by this packet. |

## Core Ownership Decision (inherited, restated for sessions)

```text
Sachima / FlowWeaver (caller) OWNS:
  - durable product/transaction/Activity state, and now durable SessionRecord / TurnRecord /
    CancellationRequestRecord state (design labels)
  - leases / epochs / state versions / idempotency / budgets
  - role mapping and the session-capable role allowlist (design label; empty today)
  - the business decision WHETHER a session may be requested, a turn sent, a close/abort issued,
    or a cancellation requested
  - caller verdicts; the supervisor library never sets a business verdict

agent-run-supervisor REMAINS an independent local supervision library:
  - owns local run/session process internals and redacted evidence artifacts
  - ONLY once invoked by an approved caller through the public boundary
  - never owns durable product/session state, leases, idempotency, or business decisions

The Gateway is NOT a caller, NOT a lifecycle owner, NOT a renderer, NOT a delivery surface.
Feishu/IM is NOT involved. No live, public, or production surface is involved.
A durable runtime (Temporal or otherwise) remains a FUTURE caller-supplied abstraction; nothing here
starts or owns a Worker, service, CLI, Docker container, socket, Gateway, or IM lifecycle.
```

## Persistent Session Model (DESIGN ONLY)

All names below are **design labels**. Nothing in this section is implemented or approved for execution by this packet.

### Prerequisites (all mandatory before any future session implementation may even be requested)

```text
1. local-only:    sessions exist only as host-local supervisor sessions; no network, Gateway, Feishu,
                  public ingress, or delivery surface anywhere in the path.
2. default-off:   a session surface ships disabled; enabling requires the exact future approval token,
                  enabled=True, and an explicit operator gate per work-starting operation.
3. caller-owned:  only a Sachima/FlowWeaver controller may call; durable session state lives caller-side.
4. role-bound:    a session binds exactly one allowlisted role_key at create time; the session-capable
                  role allowlist is a NEW design label and is EMPTY today (the Phase C capability gate
                  rejects persistent session strategies); turns cannot switch roles; first session roles
                  must remain read-only capability profiles.
5. pinned runner: pinned local acpx provenance (absolute local binary, exact role-file sha256, npx-shaped
                  basenames rejected, no network fetch) exactly as proven in Phase C/D.
6. pinned library: agent_run_supervisor importable and exactly pinned (supervisor_library.py checker)
                  before any session-bearing invocation.
7. preflight binding: a durable-state preflight record (PR #107 surface or its session-shaped successor)
                  binding the same transaction/operation with matching lease id/epoch/holder and state version.
8. budgets:       explicit caller-owned bounds set at create time: max_turns, max_artifacts per turn,
                  max evidence size markers, and a bounded session lifetime marker; exceeding any bound
                  fails closed with activity_budget_exceeded.
```

### Records (design labels)

```text
SessionRecord
- session_id            caller-owned opaque local id (never a platform id)
- activity_ref          claim-check ref to the owning ActivityRecord
- transaction_ref       claim-check ref to the Sachima/FlowWeaver transaction
- operation_ref         claim-check ref to the operation/intention record
- role_key              allowlisted session-capable role key (never raw role JSON)
- role_file_digest      sha256 of the pinned role file (Phase C provenance discipline)
- runner_provenance_ref sanitized provenance marker (never an arbitrary absolute path)
- session_binding       opaque caller-owned token binding the durable record to the supervisor-side local
                        session identity for the CURRENT lease_epoch; re-validated on every operation;
                        a mismatch fails closed (activity_session_binding_mismatch)
- lifecycle_state       stable code (see lifecycle states)
- lease_id / lease_epoch / lease_holder_ref   as in PR #102
- state_version         monotonic optimistic-concurrency version
- turn_count            non-negative integer
- open_turn_index       in-flight turn index or null (at most ONE in-flight turn per session)
- budget markers        max_turns / max_artifacts / evidence-size / lifetime markers (sanitized)
- evidence_ref/digest   sanitized session-level evidence ref + sha256, or null
- error_code            stable sanitized code or null
- caller_verdict        caller-owned or null; the library never sets it

TurnRecord (append-only, per SessionRecord)
- turn_index            monotonic, starts at 1, assigned under the claim/CAS
- idempotency_key       stable key for exactly-once turn-launch attempts
- request_fingerprint   digest of the sanitized turn request
- prompt_ref            claim-check ref only (prompt materialization stays a separately gated seam)
- status                stable turn status code (claimed_in_progress | completed | failed_retryable |
                        failed_terminal | turn_ambiguous)
- lease_epoch_at_launch epoch bound into the launch for finalize-time CAS validation
- error_code            stable code or null
- evidence_ref/digest   sanitized per-turn evidence, or null
- artifact_ref_count    non-negative integer
```

### Lifecycle states (design labels)

```text
session_requested -> session_validated -> session_opening -> session_open
session_open      -> session_turn (one in-flight TurnRecord) -> session_open
session_open | session_turn -> session_closing -> session_closed        (graceful)
session_open | session_turn -> session_aborting -> session_aborted      (forced terminal; operator-gated)
any non-terminal  -> session_failed                                      (stable error code)
cancel_requested  = durable annotation on a session/turn (see Cancellation Model); NOT a supervisor signal here

Terminal:  session_closed | session_aborted | session_failed
Ambiguous: a session/turn whose underlying local state cannot be safely determined is held in its last
           durable state with error_code set (activity_session_stale_state / activity_session_turn_ambiguous)
           and requires operator intervention; it must never be silently revived or duplicated.
```

Every transition is guarded by: exact approval gate + default-off enabled + mode/role allowlist + material screen + lease holder/epoch check + `session_binding` check + idempotency check + optimistic `state_version` check — the PR #102 guard stack plus the session binding.

### Command semantics (design labels; caller-facing)

| Command | Semantics | Hard rules |
|---|---|---|
| `session_create` | Validate the full prerequisite stack; CAS-claim a new `SessionRecord` (at most ONE non-terminal session per `activity_ref`); transition to `session_open` only on supervisor open evidence. | Duplicate create with same (idempotency_key, fingerprint) replays the stored record without opening a second local session; an existing non-terminal session for the same activity fails closed (`activity_session_already_open`); conflicting fingerprints fail closed. |
| `session_send` (turn) | Acquire/confirm the lease, then **re-read the durable record and re-check `lifecycle_state == session_open` and `open_turn_index is null` INSIDE the lease and BEFORE any launch**; CAS-append a `claimed_in_progress` TurnRecord; release the store lock; only then invoke the supervisor boundary; finalize under the lock with epoch/version CAS. | A send against a non-open session fails closed (`activity_session_not_open`); a second concurrent send fails closed pre-launch (single in-flight turn); identical replay returns the stored terminal turn (no second launch); a finalize whose lease epoch / state version moved fails closed (`activity_session_toctou_conflict`). |
| `session_query` | Read-only sanitized projection of `SessionRecord` + latest `TurnRecord` from durable state only. | Must NOT contact the live session or the supervisor. The seam-level `session_status` (a bounded local status call) is the ONLY candidate for a later, explicitly approved bounded local liveness probe; it is not allowed by this packet. |
| `session_list` | Read-only enumeration of sanitized projections filtered by transaction ref / lifecycle state. | Same projection-only rule as `session_query`; never touches live sessions. |
| `session_close` | Graceful terminal: inside the lifecycle guard, re-read current state; valid from `session_open` (no in-flight turn) or after the in-flight turn reaches terminal; write `session_closing` -> `session_closed`; release the lease only after the terminal write. | Closing an already-terminal session replays the terminal projection idempotently — it must NOT issue a second supervisor close (no double-close); close with a live in-flight turn fails closed (`activity_lifecycle_conflict`) unless escalated to `session_abort`. |
| `session_abort` | Forced terminal: operator-gated; inside the lifecycle guard, re-read current state; valid from `session_open` or `session_turn`; records `session_aborting` before any future supervisor-side interrupt could run; terminal `session_aborted` with sanitized evidence. | Abort never silently kills: the durable intent is recorded first; abort of an already-terminal session replays idempotently; ambiguous underlying state collapses to fail-closed ambiguity, never to a retry-launch. |

`close` / `abort` / `cancel` are **lifecycle-guard operations**: each must re-read the durable state inside its guarded critical section (same lock + lease epoch + state version) and decide from that fresh read — never from a stale earlier read.

### Lock ordering (explicit, stable)

```text
Order (always acquire in this order, release in reverse):
  1. durable claim/session store lock (single in-process mutex in a first slice, as proven in PR #114)
  2. per-record lifecycle guard (re-read + CAS on lease_epoch + state_version)
  3. (future implementation only) supervisor-side session handle

Rules:
- NEVER hold the store lock across a supervisor invocation. The proven Phase C discipline applies:
  claim under the lock, release, invoke outside the lock, finalize under the lock with epoch/version CAS.
- NEVER acquire the store lock while holding a supervisor session handle (no reverse order, no lock cycles).
- Multi-record operations (e.g. session_list snapshots) take read-only projections; if a future
  implementation must lock multiple records it acquires them in ascending record-id order only.
```

## Cancellation Model (DESIGN ONLY)

### Request vs execution

```text
cancellation REQUEST  = a durable, caller-owned record of intent to stop a session/turn. Design-only here.
cancellation EXECUTION = actually interrupting a local run/session process and proving cleanup. NOT APPROVED.
```

This packet designs the request record and the execution requirements. **Cancellation execution remains not approved**, and even the request record is design-only until a separately approved implementation gate. The seam deliberately has no cancel/rollback mode today; cancellation execution would require new, separately designed supervisor-side support.

### CancellationRequestRecord (design label)

```text
CancellationRequestRecord
- cancel_id             caller-owned opaque id
- session_id            target session (and optional turn_index for turn-scoped cancel)
- requested_by_ref      sanitized caller/operator ref (never a platform id)
- operator_gate         explicit human operator gate marker (mandatory; no autonomous cancellation)
- lease_id / lease_epoch  lease binding at request time; a cancel applied under a stale epoch fails closed
- idempotency_key / request_fingerprint   repeated identical cancel requests replay the stored record and
                        NEVER issue a second interruption; conflicting fingerprints fail closed
- reason_code           stable code only (never free text)
- status                cancel_requested -> cancelled | cancel_failed | cancel_ambiguous   (design labels)
- evidence_ref/digest   sanitized cancellation evidence, or null
- error_code            stable code or null
```

Terminal/ambiguous semantics:

```text
cancelled        proven terminal: the underlying run/session verifiably stopped AND cleanup evidence exists.
cancel_failed    an (future, separately approved) execution attempt ran and verifiably failed; session state
                 remains authoritative; fail closed, operator decides.
cancel_ambiguous it cannot be safely determined whether the underlying run stopped. Fail closed: the session
                 is held with error_code activity_cancel_ambiguous, no retry-launch, no duplicate interrupt,
                 operator intervention required.
In this phase, ANY cancel attempt is answered with activity_cancel_not_approved — there is no approved path.
```

### Future requirements before cancellation execution can be implemented (gate list, not approval)

```text
1. supervisor support: agent-run-supervisor must expose a documented, testable session/run interrupt API
   with stable, sanitized result semantics (the seam has none today — deliberately).
2. external process/session identity binding: the durable session_binding must bind to a verified
   supervisor-side session/run identity + epoch so a cancel can NEVER target a recycled, restarted, or
   different local process (no PID-reuse class mistakes).
3. cleanup guarantees: defined cleanup of child processes, temp/session dirs, and leases; the Phase D
   "no leftover acpx/codex processes" check generalizes into a mandatory post-cancel assertion.
4. no double-close: cancel-after-close, close-after-cancel, and cancel-after-cancel must collapse
   idempotently to the stored terminal state; a second interrupt signal must be structurally impossible.
5. artifact partial handling: partially produced artifacts are counted and labeled with stable status codes,
   kept sanitized, and never auto-delivered anywhere.
6. redacted evidence: cancellation evidence follows the same no-leak rules as all other evidence
   (stable codes, refs, digests, counts only).
7. race regression tests: cancel vs send, cancel vs close, cancel vs cancel, cancel vs lease steal/renewal,
   and cancel during finalize must each have explicit fail-closed regression tests in the implementing PR.
8. a separately named approval token narrower than live rollout, plus operator gate per cancel.
```

## Idempotency, TOCTOU, Stale-State, and Retry-Ambiguity Rules

These extend the PR #102 rules to the persistent-session lifecycle; the PR #102 rules remain in force.

```text
Lease-internal open-state recheck (work-starting operations):
- session_send (and any future work-starting session operation) MUST, after acquiring the lease and inside
  the store lock, re-read the durable record and re-check lifecycle_state == session_open AND
  open_turn_index is null BEFORE any launch. A check done before lease acquisition does not count.

Lifecycle guard (close/abort/cancel):
- close, abort, and cancel MUST re-read the durable state inside their guarded critical section (same lock,
  same lease epoch, same state_version window) and decide from the fresh read. Acting on a stale read is
  activity_session_stale_state / activity_session_toctou_conflict by definition.

Stable lock ordering:
- The explicit order above (store lock -> lifecycle guard -> future supervisor handle) is mandatory;
  no supervisor call under the store lock; no reverse acquisition; ascending record-id order for any
  multi-record locking.

Idempotency:
- The unit of exactly-once is (idempotency_key, request_fingerprint) per command, bound to lease_epoch.
- Identical replays return stored state without launching/opening/closing/interrupting anything twice.
- Same key + different fingerprint fails closed (activity_idempotency_conflict).

Stale state / TOCTOU:
- Every durable transition CASes on state_version AND lease_epoch; stale writers fail closed
  (activity_session_stale_state); drift between validation and apply fails closed
  (activity_session_toctou_conflict). Stale readers are harmless but must never be promoted into writes.

Retry ambiguity / fail-closed:
- If a prior turn/session operation's terminal state cannot be safely determined (e.g. an interrupted
  launch with no committed terminal TurnRecord, or an unverifiable local process state), the operation
  fails closed (activity_session_turn_ambiguous / activity_cancel_ambiguous) and requires operator
  intervention. A future implementation MUST NOT duplicate-launch a run, re-open a session, or re-send a
  turn merely to resolve ambiguity.

Race regression tests (required in any future implementation, not run by this PR):
- concurrent identical session_create -> exactly one open; concurrent conflicting create -> fail closed;
- concurrent session_send vs session_send -> exactly one in-flight turn;
- session_send vs session_close/abort race -> either clean turn-then-close or fail-closed conflict, never
  a turn launched into a closing/closed session;
- close vs close / abort vs abort / cancel vs cancel -> idempotent single terminal;
- lease steal/renewal during in-flight turn -> finalize CAS fails closed on the stale epoch;
- a lock-removal mutation check (as in PR #114) proving the concurrency tests actually depend on the lock.
```

## No-Leak, Durable-State, and Log Rules

Durable session/turn/cancellation state, query projections, and logs may store **only**:

```text
stable status / error / reason codes
mode / phase / lifecycle-state labels
caller-owned activity / transaction / operation / session / cancel refs and ids
role key (never raw role JSON) and role-file sha256 digest
claim-check refs and sha256 digests (never raw prompt/context)
artifact / evidence refs and sha256 digests; artifact ref counts
turn indices, attempt indices, retry counters, budget markers
lease_id / lease_epoch / lease_holder_ref / state_version (opaque, non-secret)
session_binding as an opaque caller-owned token (never a PID, socket, or raw path)
caller verdict code (caller-owned; the library never sets it)
sanitized runner-provenance markers and view-model ref digests
```

They must **never** store or log:

```text
raw prompt / context / model output / tool output
raw acpx/ACP stdout or stderr
card JSON
media bytes or media paths
platform private ids (oc_ / ou_ / om_ and similar)
raw exception text or tracebacks
tokens / credentials / cookies / secrets / raw signatures
arbitrary absolute paths from IM/user text (including session/run/evidence paths)
live process identifiers presented as durable state (PIDs, sockets, ports)
```

Log rule: logs follow exactly the same allow/forbid lists. A supervisor failure is logged as a stable code only (`activity_supervisor_failed` collapse, as merged in PR #99/#114); raw detail is suppressed.

## Failure Taxonomy (Stable Codes)

The PR #102 taxonomy and the PR #114 additions remain in force (`activity_disabled`, `activity_approval_mismatch`, `activity_unsupported_mode`, `activity_unknown_role`, `activity_unsafe_material`, `activity_idempotency_conflict`, `activity_stale_state`, `activity_lease_lost`, `activity_toctou_conflict`, `activity_retry_ambiguous`, `activity_precondition_unmet`, `activity_budget_exceeded`, `activity_supervisor_failed`, `activity_evidence_write_failed`, `activity_not_found`, `activity_runner_provenance_unverified`, `activity_role_capability_rejected`, `activity_claim_conflict`). Phase E adds session/cancellation-specific codes:

| Error code | Meaning |
|---|---|
| `activity_session_disabled` | Session surface gate not enabled (default-off). |
| `activity_session_approval_mismatch` | Exact session approval token missing or wrong. |
| `activity_session_already_open` | A non-terminal session already exists for the activity (or a create conflicts with a resident session claim). |
| `activity_session_not_open` | A work-starting operation (e.g. send) targeted a session that is not `session_open` at the lease-internal recheck. |
| `activity_session_binding_mismatch` | Durable `session_binding` does not match the bound supervisor-side session identity/epoch; fail closed, never re-bind silently. |
| `activity_session_lease_lost` | Caller no longer holds the current lease (id + epoch) over the session record. |
| `activity_session_stale_state` | Stale `state_version` / `lease_epoch` on a session transition, or a lifecycle decision made from a stale read. |
| `activity_session_toctou_conflict` | Session record drift between validation and durable apply (including finalize-time CAS failures after a launch). |
| `activity_session_turn_ambiguous` | A turn's terminal state cannot be safely determined; fail closed, no duplicate launch, operator intervention required. |
| `activity_cancel_not_approved` | Any cancellation attempt in the current phase: cancellation execution has no approved path. |
| `activity_cancel_ambiguous` | It cannot be safely determined whether a cancelled run actually stopped; fail closed, no duplicate interrupt. |
| `activity_lifecycle_conflict` | Conflicting lifecycle operations (e.g. close with an in-flight turn, send during closing, double terminal transition attempt). |
| `activity_budget_exceeded` | A caller-owned session budget bound (turns/artifacts/evidence/lifetime) would be exceeded. |
| `activity_supervisor_failed` | Supervisor invocation failed or returned unsafe fields; raw detail suppressed (inherited collapse rule). |

## Future Implementation Gates (after this design merges; each needs its own approval)

Two candidate first-implementation shapes were considered:

```text
Option A (RECOMMENDED): local/offline persistent-session lifecycle preflight / state-machine slice
  - implements SessionRecord/TurnRecord/CancellationRequestRecord shapes, lifecycle states, lease/epoch/
    binding/state-version guards, lease-internal open-state recheck, lifecycle guard, lock ordering, and the
    full fail-closed taxonomy ABOVE — with injected fakes only;
  - NO real session launch, NO supervisor session call, NO acpx, NO cancellation execution;
  - the session-shaped successor of the proven PR #107 preflight + PR #114 claim/CAS pattern, including the
    true-concurrency race regression tests listed above.

Option B (NOT recommended yet): bounded local persistent-session implementation
  - one real local read-only session (create -> N bounded turns -> close) through pinned local acpx,
    mirroring the Phase D smoke discipline;
  - only sensible AFTER Option A's state machine and race tests are merged and reviewed, and only under a
    further separate approval; still no live/Gateway/Feishu/production/real delivery and no cancellation
    execution.
```

**Recommendation: Option A.** Every prior step of this mainline earned execution by first proving its state machine fail-closed with injected fakes (design → preflight → wrapper → smoke). Persistent sessions add the highest-concurrency semantics so far (in-flight turns, lifecycle races, lease steals); those races must be regression-tested in a slice that cannot start a process at all. Option B (and later, separately, any cancellation-execution slice per the gate list above) follows only after Option A evidence. Both options must remain local/offline, default-off, with **no live, no Gateway, no Feishu, no production config, no real delivery**.

## Verification Gates (this docs-only PR)

Run by Hermes; the author does not commit, push, merge, or execute runtime code.

- [ ] Status markers present and unambiguous (all 11 markers above).
- [ ] User approval phrase quoted verbatim and interpreted as docs-only.
- [ ] Goal trace links Goal → Gap → Phase → Task → Test → Evidence → Decision.
- [ ] Manifest YAML parses with required keys (`phase_id`, `level: level-3`, `status: design_pr_open_pending_merge_decision`, scope booleans all-false on execution/live/production/delivery axes, `docs_only: true`, `strongest_allowed_outcome`).
- [ ] Status sync: `docs/roadmap/current-status.md` updated consistently (latest fields, phase-map row, references, tails, next allowed request) with PR #123 open / pending-merge wording (no merge commit invented).
- [ ] Changed-file allowlist: exactly the 4 docs/status paths in the manifest; no other file touched.
- [ ] No source diff: `git diff` contains no changes under `sachima_supervisor/`, `tests/`, roles JSON, configs, or any runtime/service file.
- [ ] Secret-shaped / no-leak scan over the four files passes.
- [ ] Forbidden-surface scan: no Gateway/Feishu/IM/webhook/acpx-invocation/npx/subprocess/service-restart instructions introduced as runnable steps.
- [ ] Optional, Hermes' choice: `pytest -q tests/sachima_supervisor` (unchanged suite stays green) and `python3 -m compileall -q sachima_supervisor tests/sachima_supervisor` — these validate the worktree, not this packet's content.
- [ ] CodeGraph status healthy in this worktree (or N/A for a docs-only worktree per AGENTS.md).
- [ ] Codex CLI primary blocker review from a fresh context: `VERDICT: PASS`, `BLOCKERS: None` required before PR completion.

## Explicit Non-Approvals

This design packet does **not** approve:

```text
implementation_of_any_kind
persistent_session_execution
persistent_session_preflight_or_state_machine_implementation (needs its own approval token)
cancellation_execution
cancellation_request_record_implementation (needs its own approval token)
session_capable_role_configs_or_role_allowlist_changes
real_local_exec
additional_real_local_smoke_execution
additional_real_agent_execution
additional_acpx_invocation
npx_fallback_or_network_fetch_evidence
write_capable_claude_or_codex_roles
satine_or_hermes_profile_acp_execution
controlled_ai_flow_execution
real_external_sachima_ingress
production_durable_runtime_code_implementation
real_external_delivery
production_delivery_control
production_agent_tool_execution_expansion
production_config_write
gateway_involvement_or_mutation
gateway_restart_or_reload
platform_adapter_mutation
gateway_owned_temporal_lifecycle
gateway_as_caller_or_renderer_or_delivery_surface
external_temporal_service_or_worker_startup
real_send_api_or_external_im_call
feishu_or_im_delivery
live_or_default_on_behavior
public_webhook_exposure
automatic_replies
worker_auto_routing
agent_to_agent_auto_routing
@all_fanout
trusted_markdown_html_rendering
```

## User Review Packet

**What this PR is:** a docs-only Phase E design gate. It defines — on paper only — how persistent local supervisor sessions (create/send/query/close/abort/list) and cancellation (request vs execution) must behave before any of it may ever be implemented: who owns what, how turns bind to leases and open-state rechecks, how close/abort/cancel re-read state inside a lifecycle guard, the stable lock ordering, the fail-closed rules for ambiguous state, the no-leak durable-state rules, and the stable failure codes.

**What it changes:** 4 docs/status files. No code, no tests, no roles, no config, no runtime, no service, no Gateway/Feishu, no acpx/AGENT process, no delivery.

**What approving the NEXT step would mean:** if this design merges and you later want the first implementation slice, the recommended next request is the **local/offline persistent-session lifecycle preflight / state-machine slice (Option A)** — injected fakes only, no real session launch, no cancellation execution. The exact approval phrase for that future gate is:

```text
approve_agent_run_supervisor_sachima_phase_e_persistent_session_lifecycle_preflight_state_machine_local_offline_implementation_no_real_session_launch_no_cancellation_execution_no_real_agent_execution_no_live_no_gateway_no_feishu_no_production_config_no_real_delivery
```

That phrase is deliberately **narrower than any session rollout**: it would approve only a fail-closed local/offline state machine exercised with injected fakes. It would NOT approve opening a real session, sending a real turn, cancelling anything, running any AGENT/acpx, or touching live/Gateway/Feishu/production/delivery surfaces.

**What stays blocked regardless:** persistent session execution, cancellation execution, additional real AGENT/acpx execution, write-capable roles, Satine/Hermes-profile ACP, controlled AI FLOW execution, live/default-on behavior, Gateway/Feishu/IM involvement, public ingress, production config writes, service restarts, platform adapter mutation, and real delivery — each requires its own separately named approval.
