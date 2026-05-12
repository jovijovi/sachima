# FlowWeaver PE-2 Design Packet — Controlled Runtime + Fake Delivery Closure

> **For Hermes:** This is a design packet only. Do not implement PE-2 from this document unless Dog Brother later gives the exact implementation approval named in this packet. Use TDD, `subagent-driven-development`, and fresh blocker review for that later implementation.

**Goal:** Define the smallest behavior-bearing PE-2 implementation slice that connects controlled Sachima ingress facts, caller-supplied FlowWeaver runtime operations, and Phase B fake-send ACK evidence without live/default-on behavior.

**Architecture:** PE-2A should be a default-off, loopback/synthetic-only runtime-delivery bridge. It consumes a sanitized Sachima turn envelope, starts or updates a FlowWeaver transaction through a caller-supplied runtime control surface, routes delivery through the existing local fake-send simulator, records ACKs only from fake-send responses, and writes sanitized evidence. It must not expose real external ingress, own Temporal lifecycle, restart Gateway, mutate production config, call real IM delivery, or run production agent/tool execution.

**Tech Stack:** Python, existing Sachima Gateway adapter contracts, `gateway.flowweaver_production_shadow_observation`, `gateway.flowweaver_temporal_observation_bridge`, `gateway.sachima_fake_send_simulator`, `gateway.delivery_state`, pytest, docs/changed-file/no-leak gates.

---

## Status Markers

```text
PE2_DESIGN_PACKET_ONLY
PE2_IMPLEMENTATION_NOT_APPROVED
PE2_LIVE_DEFAULT_ON_NOT_APPROVED
PE2_REAL_EXTERNAL_INGRESS_NOT_APPROVED
PE2_REAL_DELIVERY_NOT_APPROVED
PE2_PRODUCTION_CONFIG_WRITE_NOT_APPROVED
PE2_GATEWAY_RESTART_NOT_APPROVED
PE2_PLATFORM_ADAPTER_MUTATION_NOT_APPROVED
PE2_GATEWAY_OWNED_TEMPORAL_LIFECYCLE_NOT_APPROVED
```

Strongest allowed outcome of this PR:

```text
pe2_design_ready_for_separate_pe2a_implementation_request
```

That outcome means the next implementation request can be asked for. It does not mean implementation, live behavior, public ingress, production runtime, real delivery, config writes, or Gateway restart are approved.

## Approval and Boundary

User-facing approval text received in the chat:

```text
approve_pe2_design_packet
```

The same message also used the word implementation, but this packet deliberately applies the narrower approved token: **design packet only**. Existing project docs still mark `pe2_implementation` as NO-GO until a later, separately named implementation approval.

This design packet does **not** approve:

```text
pe2_implementation
pe2_live_default_on
real_external_sachima_ingress
production_delivery_control
production_agent_tool_execution_expansion
production_config_write
gateway_restart_or_reload
platform_adapter_mutation
gateway_owned_temporal_lifecycle
real_send_api_or_external_im_call
external_temporal_service_or_worker_startup
```

The future PE-2A implementation approval text should be:

```text
approve_pe2a_controlled_runtime_fake_delivery_implementation_no_live_no_real_external_ingress
```

If the desired next phase includes public ingress, real send APIs, production config writes, Gateway restart/reload, a Temporal service/Worker, or production AI execution, it is not PE-2A and needs a separate approval packet.

## Goal Trace

```text
Goal: Sachima becomes Dog Brother's safe, durable, observable IM AI workbench.
Gap: PE-1D proved loopback observation and Phase B proved fake-send delivery/ACKs, but no packet yet defines the smallest PE-2 implementation bridge between ingress, runtime, delivery ACKs, rollback, and evidence.
Phase: P3 — PE-2 design packet only.
Task: Define the PE-2A implementation slice, contracts, future tests, no-leak gates, changed-file guard, rollback strategy, tail state, and next approval text.
Test: Docs gate, manifest gate, changed-file guard, consistency review, security/low-intrusion review.
Evidence: This plan, manifest, dev log, PR review output, CI result.
Decision: May request PE-2A implementation only if reviews and gates pass; live/default-on and real external effects remain blocked.
```

## Level Selection

**Level 3 — High Risk.**

Reason: PE-2 design touches production-adjacent ingress, runtime operations, delivery/ACK semantics, rollback, and no-leak boundaries. Even though this PR is docs-only, ambiguity here would become live implementation risk.

## Evidence Inputs

| Evidence | Current result | PE-2 design impact |
|---|---|---|
| `GOAL.md` | Requires safety before live capability, low intrusion, separate approvals, claim-check discipline, and delivery separation. | PE-2A must stay default-off, references-only, and approval-gated. |
| PE-1D evidence | `PASS_WITH_ENVIRONMENT_NOTE`, score `92`, 8 signed turns plus restore, 9 `start_transaction`/`query_transaction` pairs, no delivery ACKs, no local sends, no-leak pass. | PE-2A can build from observation-only runtime start/query but must keep exact-port `8788` as a WATCH tail. |
| Phase B fake-send evidence | 7 send attempts, 5 accepted transcript rows, 5 ACK updates, 1 duplicate replay, 1 rejected uninitialized ref, no-leak pass. | PE-2A may use fake-send ACKs as a local delivery source; ACKs must still be derived only from accepted fake-send responses. |
| `gateway.flowweaver_production_shadow_observation` | PE-1 only calls `start_transaction` and `query_transaction`, with delivery control unchanged. | PE-2A can expand operations only through an explicit caller-supplied control surface and tests proving the new operation set. |
| `gateway.sachima_fake_send_simulator` | Local-only fake `/send` endpoint, sanitized transcript, fail-closed delivery refs. | PE-2A should reuse this simulator instead of real delivery paths. |
| `gateway.delivery_state` | Final text is only skipped when explicitly marked sent; rich-card delivery does not imply final text. | PE-2A must preserve separate surfaces and final-text delivery. |

## PE-2A Scope Decision

PE-2A is **not** full production PE-2. PE-2A is the smallest implementation slice that proves runtime-delivery closure locally.

### PE-2A may implement

1. A new default-off PE-2 bridge module, suggested path:
   - `gateway/flowweaver_pe2_controlled_runtime_delivery_bridge.py`
2. A sanitized ingress-envelope contract that accepts only reduced Sachima facts:
   - platform label `sachima`;
   - session/turn labels or digests, not real platform IDs;
   - visible surface counts;
   - claim-check refs for input, artifact, and delivery slots;
   - HMAC/auth result labels, not raw headers or signatures.
3. A caller-supplied runtime control surface interface:
   - accepts operation dictionaries;
   - never constructs Temporal clients;
   - never starts Workers, task queues, services, daemons, Docker, sockets, subprocesses, or Gateway lifecycle.
4. A bounded PE-2A runtime operation set:
   - `start_transaction`;
   - `record_operation`;
   - `plan_delivery`;
   - `record_delivery_ack`;
   - `query_transaction`;
   - optional `cancel_transaction` only for rollback/kill criteria tests.
5. Local fake delivery closure using Phase B simulator semantics:
   - allowed surfaces: `progress_card`, `rich_card`, `final_text`, `media`, `artifact`;
   - initialized delivery refs only;
   - ACK updates only after fake `/send` accepts a request;
   - duplicate replay returns duplicate ACK without appending a transcript row.
6. A sanitized PE-2A evidence writer under local `outputs/` during tests/smoke only.
7. Docs/runbook entries for start, pause/disable, rollback, restore, evidence extraction, and next approval boundaries.

### PE-2A must not implement

```text
public_webhook_exposure
reverse_proxy_or_tls_config
production_config_write
gateway_restart_or_reload
platform_adapter_mutation
real_external_send_api
production_delivery_control
production_agent_tool_execution_expansion
Temporal_Client_connect
Temporal_Worker_start
Temporal_test_environment_start
subprocess_or_Docker_or_daemon_lifecycle
raw_prompt_or_platform_payload_persistence
```

## Contracts

### 1. Sanitized PE-2A ingress envelope

The future bridge should consume a reduced envelope shaped like this:

```json
{
  "type": "flowweaver.pe2.sachima_ingress_envelope.v0",
  "platform": "sachima",
  "source": "loopback_or_synthetic_pe2a",
  "session_label": "sachima-session-<digest>",
  "turn_label": "sachima-turn-<digest>",
  "turn_discriminator": "sha256:<digest>",
  "auth": {"hmac_verified": true, "policy_label": "allowlisted_test_operator"},
  "visible_surfaces": {"final_text": true, "rich_card_count": 1, "media_count": 0},
  "claim_refs": {
    "input_ref": "runtime_input_0",
    "delivery_refs": ["runtime_delivery_0", "runtime_delivery_1"],
    "artifact_refs": ["runtime_artifact_0"]
  },
  "side_effects": []
}
```

Forbidden in this envelope: raw request bodies, raw user text, platform chat/user/message IDs, callback payloads, card JSON, media paths/bytes, tool output, credentials, raw signatures, raw exceptions, and full agent results.

### 2. Runtime control surface request

All runtime calls go through a caller-supplied `handle(request)` method. The bridge builds bounded operation requests only:

```json
{
  "operation": "record_delivery_ack",
  "workflow_id": "flowweaver-pe2a-<digest>",
  "transaction_id": "flowweaver-pe2a-<digest>",
  "delivery_ref": "runtime_delivery_2",
  "ack_ref": "runtime_event_delivery_ack_0003",
  "surface": "final_text",
  "status": "sent",
  "side_effects": []
}
```

Runtime responses must be sanitized summaries with stable statuses and error codes only. Unknown fields, raw payload-shaped fields, or platform/private ID shaped values fail closed.

### 3. Delivery/ACK contract

PE-2A delivery may only use Phase B fake-send semantics:

```text
initialized delivery slot -> fake send request -> fake send response -> runtime record_delivery_ack -> sanitized evidence
```

Rules:

- ACKs are never invented from planned delivery slots.
- An accepted fake-send response is required before `record_delivery_ack`.
- A rejected fake-send response records a stable failure code, not a sent ACK.
- Duplicate idempotency keys reuse the prior fake message/ACK and do not produce a second transcript row.
- Emitted ACK targets are a deterministic subset/prefix of initialized delivery refs.
- `rich_card` never implies `final_text`; final text must be its own delivery slot.

### 4. Evidence packet shape

Suggested future PE-2A evidence path:

```text
outputs/sachima/pe2a-controlled-runtime-fake-delivery/pe2a_controlled_runtime_fake_delivery_evidence.json
```

Required evidence fields:

```json
{
  "type": "flowweaver.pe2a.controlled_runtime_fake_delivery_evidence.v0",
  "base_sha": "<sha>",
  "scope": {
    "loopback_or_synthetic_only": true,
    "real_external_ingress": false,
    "real_external_delivery": false,
    "gateway_restart_or_config_write": false,
    "gateway_owned_temporal_lifecycle": false,
    "production_agent_tool_execution_expansion": false
  },
  "counts": {
    "accepted_ingress_envelopes": 0,
    "runtime_start_requests": 0,
    "runtime_delivery_plan_requests": 0,
    "fake_send_requests": 0,
    "runtime_ack_updates": 0,
    "duplicates": 0,
    "rejected_probes": 0
  },
  "runtime_operations": [],
  "delivery_surface_state": {},
  "negative_probes": {},
  "rollback_restore": {},
  "no_leak_scan": {"passed": true, "raw_marker_hits": 0},
  "decision": "pe2a_evidence_ready_for_external_ingress_design_request_only"
}
```

The exact counts will be set by the future implementation plan; the important invariant is that runtime ACK updates equal accepted fake-send ACKs, not attempted sends or initialized slots.

## Rollback, Restore, and Kill Criteria

### Rollback controls

PE-2A must support all of these without production config writes:

1. `enabled=false` policy returns disabled and makes zero runtime/fake-send calls.
2. `platform_allowlist=[]` or anything other than exact Sachima PE-2A policy skips/fails closed.
3. Missing runtime control surface returns `runtime_control_surface_required` with zero side effects.
4. Missing fake-send surface fails preflight before any runtime call and returns stable delivery-disabled/fake-send-required error code.
5. Git revert removes the bridge module and docs/runbook changes.

### Restore proof

After a disable/rollback probe, restoring the local test policy should allow exactly one new accepted PE-2A turn and exactly one bounded runtime/delivery/ACK chain. Duplicate restore probes must not double-start or double-ACK.

### Kill criteria

Stop the future implementation immediately if any happens:

- raw prompt, platform payload, real platform ID, card JSON, media path/bytes, tool output, credential, signature, raw exception, or callback payload appears in runtime state, evidence, logs, transcript, or user-visible output;
- a non-loopback or public URL is called;
- implementation reads or writes `~/.hermes/config.yaml`, `.env`, or production config;
- implementation starts/stops/restarts Gateway or any Temporal service/Worker;
- ACK update occurs without an accepted fake-send response;
- duplicate replay creates a second transcript row or second runtime ACK;
- rich/progress card suppresses final text;
- runtime operations exceed the allowed PE-2A operation set;
- reviewer reports a blocker.

## Blast Radius

| Axis | PE-2A limit |
|---|---|
| Environment | Clean local git worktree and test process only |
| Network | Loopback only; dynamic local ports only |
| Users | Synthetic/local operator labels only |
| Requests | Bounded smoke window, suggested maximum 10 accepted envelopes plus negative probes |
| Delivery | Fake-send simulator only |
| Runtime | Caller-supplied fake/control surface; no Gateway-owned lifecycle |
| Data | Sanitized refs, counts, digests, statuses, stable error codes |
| Persistence | Docs plus local evidence; runtime evidence must not be committed unless separately approved |

## Future Implementation Plan

### Task 1: Add PE-2A contract description tests

**Objective:** Lock the allowed operation set and non-approvals before implementation.

**Files:**
- Create: `tests/gateway/test_flowweaver_pe2_controlled_runtime_delivery_bridge.py`
- Later create: `gateway/flowweaver_pe2_controlled_runtime_delivery_bridge.py`

**Step 1: Write failing tests**

Tests should assert that `describe_flowweaver_pe2a_contract()` returns:

- type/version fields;
- allowed operations exactly `start_transaction`, `record_operation`, `plan_delivery`, `record_delivery_ack`, `query_transaction`, optional `cancel_transaction`;
- delivery boundary `fake_send_only`;
- gateway lifecycle ownership `forbidden`;
- separate approvals list includes real external ingress, real delivery, config write, Gateway restart, production runtime lifecycle, production agent/tool execution.

**Step 2:** Run the test and confirm failure because the module does not exist.

**Step 3:** Implement only the contract descriptor.

**Step 4:** Confirm the contract test passes.

### Task 2: Add sanitized ingress-envelope validation

**Objective:** Fail closed on raw or platform-shaped material before runtime calls.

**Files:**
- Modify: `tests/gateway/test_flowweaver_pe2_controlled_runtime_delivery_bridge.py`
- Modify: `gateway/flowweaver_pe2_controlled_runtime_delivery_bridge.py`

Required RED cases:

- missing required fields;
- platform not exactly `sachima`;
- hostile string/list subclasses for platform/refs;
- real platform ID shaped values in any field;
- raw/body/card/media/tool/credential-shaped keys;
- raw exception text or traceback-shaped values;
- unknown extra fields if the contract says exact field set.

### Task 3: Add runtime control surface fail-closed behavior

**Objective:** Ensure no runtime call happens unless the caller supplies a safe `handle()` method and the policy is enabled.

Required tests:

- disabled policy -> zero runtime calls, zero fake sends;
- empty allowlist -> zero runtime calls;
- missing runtime surface -> `runtime_control_surface_required`;
- runtime exception -> stable error code without raw exception text;
- unsafe runtime output -> rejected.

### Task 4: Add PE-2A positive bridge flow

**Objective:** Prove one sanitized turn can start/query runtime, plan fake delivery, fake-send final text, and record ACK.

Expected operation order:

```text
start_transaction -> record_operation -> plan_delivery -> fake_send -> record_delivery_ack -> query_transaction
```

Expected invariants:

- runtime operations are bounded and ordered;
- fake send comes before ACK;
- final text remains separate from rich/progress cards;
- evidence contains only refs/counts/digests/statuses.

### Task 5: Add duplicate/replay and restore tests

**Objective:** Make replay behavior boring.

Required tests:

- duplicate ingress envelope with same discriminator does not start a second transaction;
- duplicate fake-send idempotency key reuses prior fake ACK;
- duplicate runtime ACK is idempotent;
- disable then restore creates exactly one additional accepted runtime/delivery chain.

### Task 6: Add negative delivery and no-leak tests

**Objective:** Prove failed sends and unsafe surfaces do not mutate ACK state.

Required tests:

- uninitialized delivery ref rejects before fake transcript row;
- fake-send timeout/failure produces stable error code;
- ACK targets are a deterministic subset/prefix of initialized refs;
- media path/card JSON/tool output/private ID/secret-shaped material is rejected;
- captured logs do not contain raw exception text.

### Task 7: Add PE-2A smoke/evidence writer

**Objective:** Produce local evidence without committing runtime artifacts.

**Files:**
- Create: `scripts/flowweaver_pe2_controlled_runtime_fake_delivery_smoke.py`
- Create: `docs/runbooks/flowweaver-pe2-controlled-runtime-fake-delivery.md`
- Modify: `docs/sachima-channel.md` only if documenting behavior, not changing runtime behavior.

Expected markers:

```text
PE2A_CONTROLLED_RUNTIME_FAKE_DELIVERY_EVIDENCE_PASS
PE2A_FINAL_GATE_PASS
PE2A_CHANGED_FILE_AND_NO_LEAK_GATE_PASS
```

Runtime evidence stays under workspace/repo-local `outputs/` and must be unstaged or copied to workspace-level outputs before commit cleanup.

## Future Changed-File Guard

For the later PE-2A implementation PR, expected allowed paths are limited to:

```text
gateway/flowweaver_pe2_controlled_runtime_delivery_bridge.py
tests/gateway/test_flowweaver_pe2_controlled_runtime_delivery_bridge.py
scripts/flowweaver_pe2_controlled_runtime_fake_delivery_smoke.py
docs/runbooks/flowweaver-pe2-controlled-runtime-fake-delivery.md
docs/dev_log/<pe2a implementation dev log>.md
docs/sachima-channel.md  # docs-only behavior note, if needed
```

Forbidden without separate approval:

```text
gateway/run.py
gateway/platforms/sachima.py
hermes config files
Gateway platform registry or tool registry writes
Temporal Worker/service startup wiring
production deployment files
real send adapter code paths
```

The guard must scan unstaged, staged, untracked, and committed `merge-base..HEAD` changes. It must inspect added lines for lifecycle bypasses such as Temporal client connect calls, Worker constructors, WorkflowEnvironment usage, subprocess module calls, container/service-manager/daemon terms, socket listener startup, dynamic import/load helpers, dynamic connect lookups, config writes, and Gateway restart/reload terms.

Any changed path outside the allowlist must fail the future PE-2A implementation gate unless the user explicitly expands scope before work begins.

## Verification Gates for This Design Packet

This docs-only PR should pass:

```bash
git diff --check
git check-ignore -v docs/plans/2026-05-12-flowweaver-pe2-design-packet.md docs/plans/2026-05-12-flowweaver-pe2-design-packet-manifest.yaml docs/dev_log/2026-05-12-flowweaver-pe2-design-packet.md || true
python - <<'PY'
from pathlib import Path
plan = Path('docs/plans/2026-05-12-flowweaver-pe2-design-packet.md').read_text()
manifest = Path('docs/plans/2026-05-12-flowweaver-pe2-design-packet-manifest.yaml').read_text()
dev = Path('docs/dev_log/2026-05-12-flowweaver-pe2-design-packet.md').read_text()
required = [
    'PE2_DESIGN_PACKET_ONLY',
    'PE2_IMPLEMENTATION_NOT_APPROVED',
    'pe2_design_ready_for_separate_pe2a_implementation_request',
    'approve_pe2a_controlled_runtime_fake_delivery_implementation_no_live_no_real_external_ingress',
]
for marker in required:
    assert marker in plan or marker in manifest or marker in dev, marker
for forbidden in ['SACHIMA_SEND_URL=' + 'http', 'Client.' + 'connect(', 'Worker' + '(', 'subprocess' + '.', 'docker' + ' run', 'system' + 'ctl']:
    assert forbidden not in plan + manifest + dev, forbidden
print('PE2_DESIGN_DOC_GATE_PASS')
PY
```

Before PR creation, run two independent reviews:

1. Consistency / phase-gate review: confirm evidence dependencies, approval boundaries, tail register, and next approval text.
2. Security / low-intrusion review: confirm no implementation/live implication, no lifecycle ownership, no real delivery/ingress, no raw-material leaks, and no changed-file guard holes.

If either review finds a blocker, patch the docs and rerun a blocker-only review.

## Tail Register

The manifest is authoritative for full tail metadata including risk, owner/DRI, acceptance method, and status. The table below is the human-readable phase summary.

| ID | Class | Description | Blocks current design packet? | Blocks PE-2A implementation? | Required before | Acceptance method |
|---|---|---|---:|---:|---|---|
| PE2-WATCH-8788 | WATCH | PE-1D used fallback loopback `18788` because default `8788` was occupied by an existing Gateway. | No | No | Real external ingress or exact-port live claim | Separate maintenance-window approval and exact-port rerun; do not kill/restart Gateway opportunistically. |
| PE2-NEXT-IMPL-APPROVAL | NEXT_PHASE | PE-2A implementation is not approved by this packet. | No | Yes | Any code implementation beyond docs | Exact approval `approve_pe2a_controlled_runtime_fake_delivery_implementation_no_live_no_real_external_ingress`. |
| PE2-NEXT-EXTERNAL-INGRESS | NEXT_PHASE | Real external Sachima ingress remains outside PE-2A. | No | No | Public/tunnel/reverse-proxy/TLS exposure | Separate threat model, approval `approve_real_external_sachima_ingress`, rollback drill, and fresh security review. |
| PE2-NEXT-PROD-RUNTIME | NEXT_PHASE | Production Temporal/durable runtime service or Worker remains outside PE-2A. | No | No | Any real Temporal service/Worker or Gateway-owned lifecycle | Separate runtime ownership design and approval; caller-supplied surface only in PE-2A. |
| PE2-PARKED-REAL-DELIVERY | PARKED | Real send API and production delivery control remain parked. | No | No | Real outbound IM delivery | Separate delivery approval after PE-2A evidence and external ingress evidence. |

## Scoring Rubric

| Category | Points |
|---|---:|
| Scope clarity and non-approval separation | 20 |
| Evidence dependency accuracy | 20 |
| PE-2A contract testability | 20 |
| No-leak / side-effect / lifecycle guard quality | 20 |
| Rollback, restore, tail, and handoff quality | 20 |

Pass threshold: **92/100**, with automatic failure on any wording that implies live/default-on, real external ingress, real delivery, production config writes, Gateway restart/reload, platform adapter mutation, Gateway-owned runtime lifecycle, or production agent/tool execution expansion.

## Decision Outcome

If this packet passes docs gate and both reviews:

```text
pe2_design_ready_for_separate_pe2a_implementation_request
```

Next allowed request:

```text
approve_pe2a_controlled_runtime_fake_delivery_implementation_no_live_no_real_external_ingress
```

Still not approved:

```text
pe2_live_default_on
real_external_sachima_ingress
production_delivery_control
production_agent_tool_execution_expansion
production_config_write
gateway_restart_or_reload
platform_adapter_mutation
gateway_owned_temporal_lifecycle
real_send_api_or_external_im_call
```
