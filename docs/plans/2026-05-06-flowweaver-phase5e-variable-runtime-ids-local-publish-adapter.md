# FlowWeaver Phase 5E Variable Runtime IDs / Local Publish Adapter Implementation Plan

> **For Hermes:** This document is the Phase 5E design gate. Do not write implementation code until the user explicitly approves this plan. After approval, implement with strict TDD, focused gates, and independent review.

**Goal:** Remove the fixed `runtime_tx_replay_corpus` live-publish trap by deriving per-shadow-turn synthetic runtime IDs and add a prototype-only local publish adapter that can consume a safe Phase 5D shadow publication summary without wiring Gateway to live Temporal.

**Architecture:** Keep Gateway production behavior unchanged. Add a pure Gateway-side runtime identity helper that derives opaque, deterministic, synthetic IDs from the already-validated FlowWeaver shadow `snapshot_ref`; extend the Phase 5A/5B/5C safe contracts to accept those variable IDs; and add a prototype-only adapter under the existing Phase 5C runtime client package that can start a supplied local runtime client and replay synthetic ACK updates from a Phase 5D summary. The adapter must require explicit invocation and an already-created caller-supplied runtime client object; no factories, no service startup, no Gateway hook, no platform adapter changes, and no global tool registration.

**Tech Stack:** Python, pytest, existing Gateway FlowWeaver helpers, existing Phase 5B/5C prototype packages. Phase 5E verification should use fake-client/static/source gates only; Temporal test-environment integration is deferred to a later separately approved phase.

---

## Current Baseline

Timestamp: 2026-05-06 01:16:24 CST +0800

Repository / branch state observed before this Phase 5E design gate:

```text
canonical repo: /home/ubuntu/workspace/hermes/repo/sachima
canonical branch: feature/sachima-channel
canonical HEAD: 604995ce48acfb9610957ad5cd8cdd24b86db9b4
PR #30 / Phase 5D: MERGED, merge commit 604995ce48acfb9610957ad5cd8cdd24b86db9b4
Phase 5E worktree: /home/ubuntu/workspace/hermes/worktrees/sachima/feat-flowweaver-phase5e-variable-runtime-ids-local-publish-adapter
Phase 5E branch: feat/flowweaver-phase5e-variable-runtime-ids-local-publish-adapter
Phase 5E base: origin/feature/sachima-channel @ 604995ce48acfb9610957ad5cd8cdd24b86db9b4
```

Canonical repo still has pre-existing untracked local items that are not part of Phase 5E:

```text
.hermes/
docs/plans/2026-04-24-sachima-channel.md
docs/superpowers/
```

Baseline focused gate in the new Phase 5E worktree:

```bash
scripts/run_tests.sh \
  tests/gateway/test_flowweaver_shadow_publisher.py \
  tests/prototypes/test_flowweaver_phase5c_runtime_client_contract.py \
  -q
```

Observed:

```text
16 passed in 0.54s
```

## Context Inspected

```text
docs/plans/2026-05-05-flowweaver-phase5-architecture-gate.md
docs/plans/2026-05-05-flowweaver-phase5d-gateway-shadow-publisher-ack-bridge.md
docs/dev_log/2026-05-05-flowweaver-phase5d-gateway-shadow-publisher-ack-bridge.md
gateway/flowweaver_shadow.py
gateway/flowweaver_runtime_contract.py
gateway/flowweaver_shadow_publisher.py
gateway/flowweaver_mock_durable.py
prototypes/flowweaver_phase5b_temporal_poc/src/flowweaver_temporal_poc/payloads.py
prototypes/flowweaver_phase5b_temporal_poc/src/flowweaver_temporal_poc/workflows.py
prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/contracts.py
prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/runtime_client.py
prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/tool_adapter.py
tests/gateway/test_flowweaver_shadow_publisher.py
tests/prototypes/test_flowweaver_phase5c_runtime_client_contract.py
tests/integration/test_flowweaver_phase5c_runtime_client_temporal.py
AGENTS.md
```

Important current facts:

1. Phase 5D intentionally leaves `gateway/flowweaver_shadow_publisher.py` using fixed POC IDs:
   - `runtime_tx_replay_corpus`
   - `runtime_event_start_runtime_tx_replay_corpus`
2. Phase 5B `payloads.py` currently hard-requires `payload.transaction_id == RUNTIME_TRANSACTION_ID`, so variable workflow IDs would not be enough; the start payload itself is still fixed.
3. Phase 5C `build_start_payload_from_safe_fields()` delegates to Phase 5B `validate_start_payload()`, so it inherits the fixed-payload limitation.
4. `FlowWeaverTransactionWorkflow.run()` already sets workflow state from `payload.transaction_id`; the workflow shape can support variable IDs once validation allows them.
5. Phase 5D plan already called out the next likely stage:

```text
Should Phase 5E be “variable synthetic runtime IDs + local runtime publish adapter” before any true Gateway → Temporal start? My recommendation: yes.
```

## Why Phase 5E

After Phase 5D, Gateway can produce a safe shadow runtime publication summary and ACK bridge evidence, but the start request still contains a fixed POC transaction ID. If we connected that to a runtime, multiple Gateway turns would collide on the same workflow ID. That is exactly the kind of bug durable systems make painfully durable.

Phase 5E should fix the identity contract first and add a prototype-only publish seam that proves the Phase 5D summary can be consumed by a local runtime client without touching production Gateway wiring.

## Approach Options

### Option A — Patch only the Gateway shadow publisher to emit variable IDs

Pros:
- Smallest Gateway-side diff.
- Immediately removes fixed IDs from Phase 5D summary.

Cons:
- Phase 5B/5C validators would still reject the variable `RuntimeStartPayload`.
- Tests could pass in Gateway but fail at the actual runtime boundary.

Verdict: **Reject.** This would hide the bug one layer down.

### Option B — Contract-first variable IDs + prototype-only local publish adapter

Pros:
- Fixes the identity contract across Gateway, Phase 5B payloads, and Phase 5C runtime client validation.
- Adds a safe adapter to consume a Phase 5D publication summary through an injected local runtime client.
- Still avoids live Gateway → Temporal wiring, production config, workers, Docker, and platform adapters.

Cons:
- Touches several contract files across Phase 5A/5B/5C/5D boundaries.
- Needs careful backward compatibility for existing fixed-ID tests and POC fixtures.

Verdict: **Recommended.** This is the narrowest path that actually removes the fixed-ID trap.

### Option C — Add direct Gateway → Temporal publish behind config

Pros:
- Looks like progress.

Cons:
- Couples production Gateway to prototype runtime code too early.
- Requires service/worker lifecycle assumptions that Phase 5D explicitly avoided.
- Turns identity bugs, ACK semantics, and runtime availability into production behavior.

Verdict: **Reject hard.** Tempting, but dumb. Not yet.

## Recommended Design

### 1. Runtime identity derivation stays pure and opaque

Create a pure helper, likely:

```text
gateway/flowweaver_runtime_identity.py
```

It should accept only an already-safe shadow `snapshot_ref` shape:

```python
{
    "snapshot_key": "flowweaver_shadow_snapshot",
    "transaction_id": "tx_<safe>",
    "correlation_id": "turn_<safe>",
    "snapshot_id": "snap_<safe>",
}
```

It returns a safe identity envelope:

```python
{
    "type": "flowweaver.gateway.runtime_identity.v0",
    "verdict": "accepted",
    "reason": "ok",
    "strategy": "shadow_ref_hash_v0",
    "transaction_id": "runtime_tx_shadow_<20-hex>",
    "workflow_id": "runtime_tx_shadow_<20-hex>",
    "idempotency_key": "runtime_event_start_shadow_<20-hex>",
    "checks": {
        "snapshot_ref_valid": True,
        "ids_synthetic": True,
        "private_markers_absent": True,
        "secret_markers_absent": True,
        "source_values_not_exported": True,
    },
    "side_effects": [],
}
```

Design rules:

- Derive the suffix from a stable SHA-256 digest of the safe shadow refs, but do not copy raw shadow refs into the runtime IDs or returned start payload.
- Accept only exact plain `dict/list/str/int/bool` shapes where relevant.
- Reject private/platform markers even after the prefix: `om_`, `oc_`, `ou_`, `chat`, `message`, `platform`, `feishu`, `lark`, `telegram`, `private`, plus secret/token/password/credential/api-key markers.
- Return stable safe rejection codes only: `invalid_snapshot_ref`, `unsafe_runtime_identity`, or `runtime_identity_error`.
- No logging, no filesystem, no Temporal import, no Gateway side effect.

### 2. Phase 5A runtime ingress envelope accepts optional identity

Modify `gateway/flowweaver_runtime_contract.py` so `build_flowweaver_runtime_ingress_envelope(...)` can accept an optional validated runtime identity. Backward-compatible default may remain the old fixed POC identity for existing corpus tests, but Phase 5D publisher must pass a derived identity.

Expected accepted envelope idempotency shape:

```python
"idempotency": {
    "strategy": "shadow_ref_hash_v0",
    "transaction_key": "runtime_tx_shadow_<20-hex>",
    "start_event_key": "runtime_event_start_shadow_<20-hex>",
    "intent_key_prefix": "runtime_intent_",
    "artifact_key_prefix": "runtime_artifact_",
    "delivery_key_prefix": "runtime_delivery_",
}
```

Backward compatibility rule:

```text
The legacy `synthetic_index_v0` / `runtime_tx_replay_corpus` identity may remain accepted for old POC fixtures, but no Phase 5D live-shadow publication path should emit it after Phase 5E.
```

### 3. Phase 5B/5C validators accept variable synthetic runtime IDs safely

Modify Phase 5B `payloads.py` and Phase 5C `contracts.py` so they accept any synthetic runtime ID that passes the strict runtime ID validator, not only `runtime_tx_replay_corpus`.

Rules:

- `transaction_id` and `workflow_id` must start with `runtime_tx_`.
- `idempotency_key` must start with `runtime_event_`.
- String length remains bounded (`<=128` unless implementation chooses stricter).
- Embedded private/platform/secret markers remain rejected, not just bad prefixes.
- `build_start_payload_from_ingress_envelope()` should return `RuntimeStartPayload(transaction_id=<envelope idempotency.transaction_key>, idempotency_key=<envelope idempotency.start_event_key>)`.
- Existing fixed POC tests stay green to preserve replay-corpus compatibility.

### 4. Phase 5D publisher emits variable IDs from the safe shadow capture

Modify `gateway/flowweaver_shadow_publisher.py` so the ready `start_request` uses the derived identity:

```python
summary["transaction_id"] == identity["transaction_id"]
summary["workflow_id"] == identity["workflow_id"]
summary["start_request"]["workflow_id"] == identity["workflow_id"]
summary["start_request"]["start_payload"]["transaction_id"] == identity["transaction_id"]
summary["start_request"]["start_payload"]["idempotency_key"] == identity["idempotency_key"]
```

The returned summary may include a narrow identity metadata block, but it must not include raw shadow refs:

```python
"runtime_identity": {
    "type": "flowweaver.gateway.runtime_identity.v0",
    "strategy": "shadow_ref_hash_v0",
    "transaction_id": "runtime_tx_shadow_<20-hex>",
    "workflow_id": "runtime_tx_shadow_<20-hex>",
    "idempotency_key": "runtime_event_start_shadow_<20-hex>",
}
```

Do **not** change `gateway/run.py` in Phase 5E. If a reviewer believes that is unavoidable, stop immediately and require a revised design plus explicit user approval before any `gateway/run.py` edit. The existing Phase 5D hook should automatically attach the updated summary once helper behavior changes.

### 5. Prototype-only local publish adapter consumes Phase 5D summaries

Add a module under the existing prototype runtime-client package, likely:

```text
prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/publication_adapter.py
```

The adapter should provide an explicit function/class such as:

```python
async def publish_shadow_runtime_publication(publication: object, *, runtime_client: object) -> dict[str, object]: ...
```

or:

```python
class FlowWeaverShadowPublicationAdapter:
    def __init__(self, runtime_client: object) -> None: ...
    async def publish(self, publication: object) -> dict[str, object]: ...
```

Adapter rules:

1. Accept only Phase 5D `flowweaver.gateway.shadow_runtime_publication.v0` summaries with `verdict == "ready"`.
2. Validate `start_request` with the same Phase 5C safe-field builder used by the tool adapter.
3. Validate each ACK bridge update with existing safe ACK validators.
4. Call `runtime_client.start_transaction(payload, workflow_id=workflow_id)` exactly once.
5. Apply ACK updates with `runtime_client.record_delivery_ack(workflow_id, update)` in input order after start succeeds.
6. Return only a safe bounded result:

```python
{
    "ok": True,
    "operation": "publish_shadow_runtime_publication",
    "workflow_id": "runtime_tx_shadow_<20-hex>",
    "transaction_id": "runtime_tx_shadow_<20-hex>",
    "status": "published",
    "runtime_call_counts": {"start_transaction": 1, "record_delivery_ack": 2},
    "ack_statuses": ["applied", "duplicate"],
}
```

7. On invalid input or runtime exception, return stable safe errors only:

```python
{"ok": False, "operation": "publish_shadow_runtime_publication", "error_code": "invalid_publication"}
{"ok": False, "operation": "publish_shadow_runtime_publication", "error_code": "invalid_start_payload"}
{"ok": False, "operation": "publish_shadow_runtime_publication", "error_code": "invalid_delivery_ack_update"}
{"ok": False, "operation": "publish_shadow_runtime_publication", "error_code": "runtime_error"}
```

8. Do not include nested runtime snapshots, raw exceptions, raw publication input, platform IDs, card JSON, delivery payloads, or secrets in the result.
9. Do not import or reference `temporalio`, MCP, Gateway, Gateway platform adapters, workflow modules, connect helpers, factories, addresses, `Client.connect`, `Worker`, `start_workflow`, `execute_update`, subprocess, Docker, or service lifecycle APIs anywhere in the adapter source.
10. Do not construct or connect runtime clients inside this adapter. It must consume an already-created caller-supplied `runtime_client` object only.

## Proposed Files

### Create after explicit Phase 5E implementation approval

```text
gateway/flowweaver_runtime_identity.py
tests/gateway/test_flowweaver_runtime_identity.py
tests/prototypes/test_flowweaver_phase5e_variable_runtime_ids.py
tests/prototypes/test_flowweaver_phase5e_local_publish_adapter.py
prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/publication_adapter.py
```

### Modify after explicit Phase 5E implementation approval

```text
gateway/flowweaver_contract.py  # blocker-driven microsecond created_at precision for per-turn identity
gateway/flowweaver_runtime_contract.py
gateway/flowweaver_shadow_publisher.py
prototypes/flowweaver_phase5b_temporal_poc/src/flowweaver_temporal_poc/payloads.py
prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/contracts.py
prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/__init__.py  # only if exporting adapter is useful
tests/gateway/test_flowweaver_shadow_publisher.py
tests/gateway/test_flowweaver_runtime_contract.py  # if exact envelope assertions live there
tests/prototypes/test_flowweaver_phase5c_runtime_client_contract.py
docs/dev_log/2026-05-06-flowweaver-phase5e-variable-runtime-ids-local-publish-adapter.md
```

### Must not modify in Phase 5E without revised user approval

```text
gateway/run.py
gateway/platforms/**
run_agent.py
model_tools.py
toolsets.py
tools/**
mcp_serve.py
~/.hermes/config.yaml
pyproject.toml  # no new dependency should be needed
```

## Implementation Tasks After Approval

### Task 1: RED tests for runtime identity derivation

**Objective:** Prove per-shadow-turn runtime IDs are deterministic, synthetic, opaque, and reject unsafe refs.

**Files:**
- Create: `tests/gateway/test_flowweaver_runtime_identity.py`

**Tests:**
- Missing module import should fail RED first.
- Same safe `snapshot_ref` produces same `transaction_id`, `workflow_id`, and `idempotency_key`.
- Different safe `snapshot_ref` produces different IDs.
- Same safe `snapshot_ref` plus different safe `created_at` turn timestamps produces different IDs.
- IDs match `runtime_tx_shadow_[a-f0-9]{20}` and `runtime_event_start_shadow_[a-f0-9]{20}`.
- Returned identity does not include raw `tx_...`, `turn_...`, or `snap_...` values.
- Private/platform markers embedded after prefixes are rejected.
- Secret-shaped strings are rejected without echoing offending values.
- Hostile `Mapping`, `str` subclasses, and mutating values are rejected before equality side effects.

**Run:**

```bash
scripts/run_tests.sh tests/gateway/test_flowweaver_runtime_identity.py -q
```

**Expected RED:** `ModuleNotFoundError` for `gateway.flowweaver_runtime_identity` or missing function.

### Task 2: Implement pure runtime identity helper

**Objective:** Add the minimal helper to pass Task 1 only.

**Files:**
- Create: `gateway/flowweaver_runtime_identity.py`

**Rules:**
- Standard library only.
- No logging.
- No Temporal/MCP/prototype imports.
- No filesystem/network/process calls.

**Run:**

```bash
scripts/run_tests.sh tests/gateway/test_flowweaver_runtime_identity.py -q
python -m py_compile gateway/flowweaver_runtime_identity.py tests/gateway/test_flowweaver_runtime_identity.py
```

**Expected GREEN:** identity tests pass.

### Task 3: RED tests for variable runtime ingress/start payload contracts

**Objective:** Prove Phase 5A/5B/5C no longer require the fixed replay-corpus ID while preserving safety.

**Files:**
- Create or modify: `tests/prototypes/test_flowweaver_phase5e_variable_runtime_ids.py`
- Modify: `tests/gateway/test_flowweaver_runtime_contract.py` if exact envelope assertions live there
- Modify: `tests/prototypes/test_flowweaver_phase5c_runtime_client_contract.py`

**Tests:**
- `build_flowweaver_runtime_ingress_envelope(..., runtime_identity=identity)` emits `transaction_key` and `start_event_key` from identity.
- Phase 5B `validate_start_payload()` accepts `RuntimeStartPayload(transaction_id="runtime_tx_shadow_<hex>", idempotency_key="runtime_event_start_shadow_<hex>", ...)`.
- Phase 5C `build_start_payload_from_safe_fields()` accepts the same variable fields.
- Existing fixed `runtime_tx_replay_corpus` fixture still passes for POC compatibility.
- IDs containing embedded `oc_`, `ou_`, `chat`, `message`, `platform`, `feishu`, `lark`, `telegram`, `private`, `token`, `secret`, `password`, or `api_key` are rejected.
- `build_start_payload_from_ingress_envelope()` returns the envelope’s variable identity, not the old fixed constants.

**Run:**

```bash
scripts/run_tests.sh \
  tests/prototypes/test_flowweaver_phase5e_variable_runtime_ids.py \
  tests/prototypes/test_flowweaver_phase5c_runtime_client_contract.py \
  -q
```

**Expected RED:** fixed-ID validator rejects the new variable payload.

### Task 4: Implement variable ID contract support

**Objective:** Update Phase 5A/5B/5C validators and envelope projection while keeping old POC fixtures green.

**Files:**
- Modify: `gateway/flowweaver_runtime_contract.py`
- Modify: `prototypes/flowweaver_phase5b_temporal_poc/src/flowweaver_temporal_poc/payloads.py`
- Modify: `prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/contracts.py`

**Run:**

```bash
scripts/run_tests.sh \
  tests/gateway/test_flowweaver_runtime_identity.py \
  tests/prototypes/test_flowweaver_phase5e_variable_runtime_ids.py \
  tests/prototypes/test_flowweaver_phase5c_runtime_client_contract.py \
  -q
python -m py_compile \
  gateway/flowweaver_contract.py \
  gateway/flowweaver_runtime_identity.py \
  gateway/flowweaver_runtime_contract.py \
  prototypes/flowweaver_phase5b_temporal_poc/src/flowweaver_temporal_poc/payloads.py \
  prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/contracts.py
```

### Task 5: RED tests for Phase 5D publisher using variable IDs

**Objective:** Prove Gateway shadow publication no longer emits fixed IDs for live-shadow summaries.

**Files:**
- Modify: `tests/gateway/test_flowweaver_shadow_publisher.py`

**Tests:**
- Ready summary `transaction_id`, `workflow_id`, and start payload ID are `runtime_tx_shadow_<hex>`.
- `runtime_tx_replay_corpus` is absent from a ready summary rendered string for a normal shadow result.
- Two different `make_shadow_agent_result(index=...)` values produce different runtime IDs.
- Same session/transaction ID with distinct subsecond shadow turn timestamps produces different runtime IDs.
- ACK bridge target IDs remain bounded synthetic delivery IDs and do not pick up identity source refs.
- Rejection paths remain stable and safe.

**Run:**

```bash
scripts/run_tests.sh tests/gateway/test_flowweaver_shadow_publisher.py -q
```

**Expected RED:** current publisher still emits `runtime_tx_replay_corpus`.

### Task 6: Implement publisher identity integration

**Objective:** Use the new identity helper and runtime-contract identity support in `gateway/flowweaver_shadow_publisher.py`.

**Files:**
- Modify: `gateway/flowweaver_shadow_publisher.py`

**Rules:**
- Do not modify `gateway/run.py`.
- Do not import Phase 5B/5C prototype packages from Gateway.
- Do not add Temporal/MCP/subprocess/service imports or calls.
- Fail closed with safe rejection reason if identity derivation fails.

**Run:**

```bash
scripts/run_tests.sh \
  tests/gateway/test_flowweaver_runtime_identity.py \
  tests/gateway/test_flowweaver_shadow_publisher.py \
  tests/gateway/test_flowweaver_shadow_publisher_run_hook.py \
  -q
python -m py_compile gateway/flowweaver_shadow_publisher.py
```

### Task 7: RED tests for prototype local publish adapter

**Objective:** Prove the adapter consumes safe Phase 5D summaries through an injected runtime client and exposes only safe results.

**Files:**
- Create: `tests/prototypes/test_flowweaver_phase5e_local_publish_adapter.py`

**Tests:**
- Source/diff scan proves `publication_adapter.py` contains no `temporalio`, `mcp`, Gateway imports, Gateway platform adapters, workflow imports, factories, address/connect helpers, `Client.connect`, `Worker`, `start_workflow`, `execute_update`, subprocess, Docker, or service lifecycle terms anywhere.
- A ready publication summary with one ACK calls fake runtime client `start_transaction()` once, then `record_delivery_ack()` once.
- Multiple ACK updates preserve order and return bounded statuses only.
- Invalid summary type/verdict/start request/ACK update returns stable safe error codes.
- Runtime exception returns `runtime_error` and does not echo raw exception text, workflow IDs, private markers, or secret-shaped strings.
- Result top-level fields are an allowlist; no nested snapshots or raw publication input are returned.
- No connect/address/factory/client-construction/service startup path exists in the adapter; tests instantiate it with an already-created fake runtime client only.

**Run:**

```bash
scripts/run_tests.sh tests/prototypes/test_flowweaver_phase5e_local_publish_adapter.py -q
```

**Expected RED:** module/function missing.

### Task 8: Implement prototype local publish adapter

**Objective:** Add the explicit prototype-only adapter using existing Phase 5C contract validators and an already-created caller-supplied runtime client object.

**Files:**
- Create: `prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/publication_adapter.py`
- Modify: `prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/__init__.py` only if needed

**Run:**

```bash
scripts/run_tests.sh tests/prototypes/test_flowweaver_phase5e_local_publish_adapter.py -q
python -m py_compile \
  prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/publication_adapter.py \
  tests/prototypes/test_flowweaver_phase5e_local_publish_adapter.py
```

### Task 9: Regression and boundary gates

**Objective:** Verify Phase 5E did not widen production surfaces.

**Focused tests:**

```bash
scripts/run_tests.sh \
  tests/gateway/test_flowweaver_runtime_identity.py \
  tests/gateway/test_flowweaver_runtime_contract.py \
  tests/gateway/test_flowweaver_shadow_publisher.py \
  tests/gateway/test_flowweaver_shadow_publisher_run_hook.py \
  tests/prototypes/test_flowweaver_phase5e_variable_runtime_ids.py \
  tests/prototypes/test_flowweaver_phase5c_runtime_client_contract.py \
  tests/prototypes/test_flowweaver_phase5c_tool_adapter.py \
  tests/prototypes/test_flowweaver_phase5e_local_publish_adapter.py \
  -q
```

**Compile:**

```bash
python -m py_compile \
  gateway/flowweaver_contract.py \
  gateway/flowweaver_runtime_identity.py \
  gateway/flowweaver_runtime_contract.py \
  gateway/flowweaver_shadow_publisher.py \
  prototypes/flowweaver_phase5b_temporal_poc/src/flowweaver_temporal_poc/payloads.py \
  prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/contracts.py \
  prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/publication_adapter.py
```

**Diff / lint:**

```bash
git diff --check
ruff check gateway/flowweaver_contract.py gateway/flowweaver_runtime_identity.py gateway/flowweaver_runtime_contract.py gateway/flowweaver_shadow_publisher.py prototypes/flowweaver_phase5b_temporal_poc/src/flowweaver_temporal_poc/payloads.py prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/contracts.py prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/publication_adapter.py
```

**Custom scans:**

- changed-file allowlist includes all staged/unstaged/untracked files.
- `gateway/run.py` must be unchanged in Phase 5E.
- no `gateway/platforms/**`, `tools/**`, `run_agent.py`, `model_tools.py`, `toolsets.py`, or `mcp_serve.py` changes.
- no production config writes, no `~/.hermes/config.yaml`, no `mcp_servers` writes.
- diff-hunk-aware scan for new Gateway lines forbids `temporalio`, `flowweaver_runtime_client`, `flowweaver_temporal_poc`, `mcp`, `subprocess`, `Popen`, `docker`, `Client.connect`, `Worker`, `start_workflow`, `execute_update`.
- prototype adapter source/diff scan proves `publication_adapter.py` contains no `temporalio`, `mcp`, Gateway imports, Gateway platform adapters, workflow imports, factories, address/connect helpers, `Client.connect`, `Worker`, `start_workflow`, `execute_update`, subprocess, Docker, or service lifecycle terms anywhere.
- secret/private-ID scan on added lines and rendered safe results; split synthetic secret strings in tests to avoid poisoning gates.
- no payload-carrying Temporal Signals; Updates remain validated.

### Task 10: Independent reviews

**Objective:** Fresh-context verification before commit/PR.

Run at least two `delegate_task` reviews:

1. Plan/spec/code review focused on variable identity consistency across Phase 5A/5B/5C/5D and the local publish adapter.
2. Security/low-intrusion review focused on no production Gateway wiring, no service lifecycle, no secret/private-ID leakage, no raw exception logging, and no unsafe Temporal-history inputs.

Reviewer blockers must be handled by adding RED tests first, then fixing code, then rerunning focused review.

## Acceptance Criteria

Phase 5E is complete only when all are true:

1. Phase 5D ready summaries for normal shadow results no longer contain `runtime_tx_replay_corpus`.
2. Runtime IDs are deterministic per safe shadow ref + safe turn timestamp, variable across turns (including subsecond same-session turns), synthetic, bounded, and opaque.
3. Phase 5B/5C start payload validators accept variable safe IDs and still reject embedded private/platform/secret markers.
4. Existing fixed POC fixtures remain supported where needed for replay-corpus tests.
5. Prototype local publish adapter can consume a Phase 5D summary using an injected runtime client/fake client and return safe bounded results.
6. No live Gateway → Temporal wiring exists.
7. No Temporal test environment, service, worker, Docker, daemon, Gateway restart, production config, global tool registration, or platform adapter change occurs.
8. No payload-carrying Temporal Signals are introduced; external writes remain validated Updates only.
9. Tests prove invalid inputs and runtime errors expose only stable safe error codes.
10. Focused tests, py_compile, diff checks, boundary scans, sensitive scans, and independent reviews pass.

## Risks / Tradeoffs

1. **Contract fan-out:** This touches Gateway contracts and two prototype packages. Mitigation: TDD across each boundary and keep old fixtures compatible.
2. **ID overexposure:** Even sanitized shadow refs may encode task words. Mitigation: derived runtime IDs should use a digest suffix, not raw refs.
3. **Validator drift:** Phase 5B and Phase 5C validators can silently diverge. Mitigation: shared tests that exercise the same variable payload through both layers.
4. **Adapter becoming production wiring by accident:** Mitigation: keep it in prototypes, require injected runtime client, no address connect path, no Gateway import, and no tool/global registry registration.
5. **Temporal history leaks:** Mitigation: validate before start/update, use no payload-carrying Signals, and defer Temporal-history integration proof to a later separately approved phase.
6. **False-positive scans:** Existing repo contains baseline service/MCP/process strings. Mitigation: use changed-file and diff-hunk-aware scans, not whole-repo greps.

## Open Questions / Recommended Answers

1. **Should Phase 5E include live Gateway → Temporal publish behind config?** No. Keep that for a later explicit phase after variable IDs and local publish adapter pass.
2. **Should the derived ID include raw safe shadow refs for debuggability?** No. Use a digest; debugging can use safe summaries and counts, not IDs that reveal source labels.
3. **Should the adapter live in a new Phase 5E prototype package?** My recommendation: no. Put it under the existing Phase 5C runtime client prototype package because it is an adapter over that facade, not a new runtime.
4. **Should Phase 5E include Temporal test-environment integration?** No. Defer it to a later separately approved phase; Phase 5E should prove the adapter with fake clients and static/source gates only.

## Approval Gate

This plan approves only Phase 5E design documentation. It does **not** approve implementation code.

Implementation must wait for explicit user approval, e.g.:

```text
批准 Phase 5E 实现
```
