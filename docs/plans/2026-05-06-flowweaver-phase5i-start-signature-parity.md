# FlowWeaver Phase 5I Start Signature Parity Implementation Plan

> **For Hermes:** User approved Phase 5I execution scope after Phase 5H merge. This document is the concrete design gate. Do not write implementation code until this plan is saved, doc-gated, and independently reviewed. If reviewers keep the scope inside this plan, proceed under the user's Phase 5I approval; stop only for scope expansion, production wiring, service lifecycle, destructive cleanup, or security blockers.

**Goal:** Remove raw start-policy material from the local Temporal workflow start payload, persist a safe start-signature summary in workflow snapshots, and use that signature during real-worker duplicate-start recovery.

**Architecture:** Keep the change prototype-only and default-off. The Gateway shadow publication may still carry the existing safe ingress contract dictionary, but the Phase 5C runtime adapter must reduce it before `start_workflow(...)` to a `RuntimeStartPayload` that contains only synthetic IDs, counts, and deterministic `runtime_sig_*` digests. `FlowWeaverTransactionWorkflow` stores and exposes the same safe signature; `FlowWeaverRuntimeClient` compares it during duplicate-start recovery. The in-memory reconciliation runtime gains the same snapshot field so fake and real snapshots stay schema-compatible. No Gateway runtime wiring, platform adapter, service lifecycle, dependency, or production config changes.

**Tech Stack:** Python, pytest, Temporal Python SDK test environment for explicitly integration-marked tests, existing Phase 5B payload/workflow contracts, Phase 5C runtime facade/sanitizer, Phase 5F/5H reconciliation harnesses. Temporal remains optional via existing extras only.

---

## Current Baseline

Timestamp: 2026-05-06 15:46:31 CST +0800

Repository state at Phase 5I start:

```text
canonical repo: /home/ubuntu/workspace/hermes/repo/sachima
canonical branch: feature/sachima-channel
canonical HEAD: f474811052fd901a83f5b318c395e5f33478c9d3
origin/feature/sachima-channel: f474811052fd901a83f5b318c395e5f33478c9d3
Phase 5H / PR #34: MERGED
Phase 5I worktree: /home/ubuntu/workspace/hermes/worktrees/sachima/feat-flowweaver-phase5i-start-signature-parity
Phase 5I branch: feat/flowweaver-phase5i-start-signature-parity
Phase 5I base: origin/feature/sachima-channel @ f474811052fd901a83f5b318c395e5f33478c9d3
```

Canonical untracked items are pre-existing and not part of Phase 5I:

```text
.hermes/
docs/plans/2026-04-24-sachima-channel.md
docs/superpowers/
```

Observed baseline evidence before code changes:

```text
# Temporal integration baseline
18 passed in 1.29s

# Expanded prototype baseline
48 passed, 1 environment/order-sensitive optional Temporal import failure

# Isolated failing prototype selector reruns
1 passed through scripts/run_tests.sh
1 passed through direct hermetic pytest
```

## Why Phase 5I

Phase 5H intentionally limited real duplicate-start mismatch detection to fields already visible in the current workflow snapshot:

```text
transaction_id
entry_count
record_counts
counts
intent/artifact/delivery key sets
side_effects
active snapshot status
```

That left two related gaps:

1. The Phase 5F fake runtime stores a full payload signature, while the real Worker currently cannot distinguish a duplicate start whose `workflow_id`, `transaction_id`, counts, and initialized slots match but whose safe start identity differs.
2. The current Temporal start input still contains raw contract policy material such as claim-check policy keys and forbidden-material names. A security reviewer verified those strings can appear in serialized Temporal history bytes. That is not acceptable for the direction FlowWeaver is moving.

Phase 5I closes both gaps before any live Gateway-to-runtime wiring. A durable runtime must make duplicate starts exact, and Temporal history must not become a museum of policy payloads we meant to keep outside the durable boundary. Cute demos can leak; durable systems do not get that luxury.

## Design Decision: Reduce Before Temporal History

Do **not** pass raw `allowed_runtime_events` or raw `claim_check_policy` into `start_workflow(...)`.

The Gateway-side publication contract can remain unchanged in this phase, because it is still default-off shadow material and existing tests depend on that shape. The runtime adapter boundary must reduce it into a Temporal-safe payload:

```python
@dataclass(frozen=True)
class RuntimeStartPayload:
    transaction_id: str
    idempotency_key: str
    entry_count: int
    record_counts: dict[str, int]
    event_contract_digest: str
    claim_policy_digest: str
```

The workflow snapshot exposes this safe start-signature summary:

```python
{
    "type": "flowweaver.temporal_poc.start_signature.v0",
    "version": "flowweaver.temporal_poc.v0",
    "idempotency_key": "runtime_event_...",
    "event_contract_digest": "runtime_sig_<hex>",
    "claim_policy_digest": "runtime_sig_<hex>",
}
```

Rules:

1. `idempotency_key` remains a safe synthetic runtime event ID.
2. `event_contract_digest` and `claim_policy_digest` are deterministic SHA-256-based safe digest IDs with prefix `runtime_sig_`.
3. Digests are computed from already-validated plain data using canonical JSON with sorted keys and stable separators; never Python `hash()`.
4. The Temporal `RuntimeStartPayload`, query snapshots, update results, tool-visible results, and history must not contain raw claim-check policy lists, raw forbidden-material names, raw platform IDs, prompts, tool output, card JSON, delivery ACK payloads, credentials, or exception text.
5. The signature helper is shared by workflow and facade code so duplicate-start comparison cannot drift.
6. Existing counts/status maps remain in the snapshot; Phase 5I adds safe signature parity and start-input reduction, not a broader workflow engine redesign.

## Scope Boundary

### In scope

1. Add deterministic digest/signature helpers to Phase 5B payload contracts.
2. Reduce `RuntimeStartPayload` so it stores only synthetic IDs, counts, and digests.
3. Update ingress/tool/publication adapters that build `RuntimeStartPayload` so they validate existing raw safe dictionaries, compute digests, and pass only reduced dataclasses to Temporal.
4. Store the signature in `FlowWeaverTransactionWorkflow` state and include it in query/update snapshots.
5. Extend Phase 5C `sanitize_snapshot()` / snapshot field whitelist to accept only the safe signature shape.
6. Compare the sanitized snapshot start signature during `FlowWeaverRuntimeClient` duplicate-start recovery.
7. Keep the in-memory reconciliation runtime schema-compatible by adding the same signature field to fake snapshots while preserving its stricter full-signature comparison outside Temporal history.
8. Add RED tests for both the current history leak and current duplicate-start false acceptance.
9. Add sanitizer/no-leak tests proving raw policy material is not exposed through the start signature or history.
10. Add a Phase 5I source-boundary gate for this branch.
11. Update docs/dev log and run focused gates + independent reviews before commit/PR.

### Out of scope

Phase 5I does **not** approve:

```text
gateway/run.py changes
gateway/platforms/** changes
run_agent.py changes
model_tools.py changes
toolsets.py changes
tools/** changes
hermes_cli/** changes
production Hermes tool registration
MCP/global registry changes
production Gateway service restart
production Gateway -> Temporal wiring
Docker / Temporal CLI / daemon / external Temporal service startup
~/.hermes/config.yaml writes
base dependency changes that install temporalio outside optional extras
payload-carrying Signals
Activities / LLM calls / shell commands inside Workflow code
remote branch deletion
PR merge
```

## Planned Files

Create:

```text
docs/plans/2026-05-06-flowweaver-phase5i-start-signature-parity.md
docs/dev_log/2026-05-06-flowweaver-phase5i-start-signature-parity.md
tests/integration/test_flowweaver_phase5i_start_signature_parity.py
tests/prototypes/test_flowweaver_phase5i_start_signature_contract.py
```

Modify:

```text
prototypes/flowweaver_phase5b_temporal_poc/src/flowweaver_temporal_poc/payloads.py
prototypes/flowweaver_phase5b_temporal_poc/src/flowweaver_temporal_poc/workflows.py
prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/contracts.py
prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/runtime_client.py
prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/reconciliation_harness.py
tests/prototypes/test_flowweaver_phase5b_temporal_payloads.py
tests/prototypes/test_flowweaver_phase5c_tool_adapter.py
tests/prototypes/test_flowweaver_phase5g_delivery_cardinality.py
```

Existing tests construct `RuntimeStartPayload` directly with raw policy fields, so those tests must be updated to use the new builder or reduced dataclass shape. This is test maintenance caused by the safer payload schema, not scope creep.

Potential test-only adjustment if full Phase 5H file is included in a broad integration selector:

```text
tests/integration/test_flowweaver_phase5h_local_temporal_worker_reconciliation.py
```

Preferred gate: run Phase 5H behavioral tests by node ID and use the new Phase 5I boundary gate for the current branch. The existing Phase 5H source-boundary test is Phase-5H-specific and compares the current branch diff against base; running that exact node after Phase 5I changes will fail by design.

## TDD Task Plan

### Task 1: RED — prove current history leak and duplicate-start false acceptance

**Objective:** Capture the two Phase 5I target failures against the current real Worker before implementation.

**Files:**

- Create: `tests/integration/test_flowweaver_phase5i_start_signature_parity.py`

Tests:

```text
test_phase5i_temporal_history_omits_raw_start_policy_after_start_duplicate_and_cancel
test_phase5i_duplicate_start_with_same_observable_counts_but_different_idempotency_is_rejected
test_phase5i_matching_duplicate_start_still_returns_running_and_replay_duplicate_acks
```

Expected RED before implementation:

1. History scan fails because serialized Temporal events contain one or more raw start-policy markers such as `claim_check_policy`, `forbidden_material`, raw policy value names, or raw start-payload field names that should not cross into history after Phase 5I.
2. Duplicate-start mismatch test fails because a second start with the same workflow ID/counts but different safe `idempotency_key` currently returns safe `running` instead of `invalid_start_payload`.
3. Matching duplicate behavior should already pass; keep it as a regression so Phase 5I does not break Phase 5H idempotency.

History scan must inspect both rendered history JSON/text and raw serialized event bytes:

```python
rendered = history.to_json() if hasattr(history, "to_json") else repr(history.to_json_dict())
raw_events = b"".join(event.SerializeToString() for event in history.events)
```

Do not count setup errors, no tests collected, or Worker lifecycle failures as valid RED.

### Task 2: RED/GREEN — define reduced start payload and safe signature contract

**Objective:** Define the reduced Temporal payload shape and snapshot signature before workflow/facade implementation.

**Files:**

- Create: `tests/prototypes/test_flowweaver_phase5i_start_signature_contract.py`
- Modify: `prototypes/flowweaver_phase5b_temporal_poc/src/flowweaver_temporal_poc/payloads.py`
- Modify: `prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/contracts.py`

Tests to add first:

```text
test_phase5i_runtime_start_payload_reduces_raw_policy_to_safe_digests
test_phase5i_start_signature_contains_idempotency_and_safe_digests_only
test_phase5i_signature_digest_changes_for_changed_event_contract_or_policy
test_phase5i_snapshot_sanitizer_accepts_safe_start_signature
test_phase5i_snapshot_sanitizer_rejects_raw_claim_policy_or_private_markers_in_signature
test_phase5i_reduced_payload_repr_omits_raw_policy_markers
```

Implementation sketch:

```python
START_SIGNATURE_TYPE = "flowweaver.temporal_poc.start_signature.v0"
RUNTIME_SIGNATURE_PREFIX = "runtime_sig_"

def build_runtime_start_payload(
    *,
    transaction_id: object,
    idempotency_key: object,
    entry_count: object,
    record_counts: object,
    allowed_runtime_events: object,
    claim_check_policy: object,
) -> RuntimeStartPayload: ...

def start_signature_from_payload(payload: RuntimeStartPayload) -> dict[str, object]: ...
```

`build_start_payload_from_ingress_envelope(...)` and Phase 5C `build_start_payload_from_safe_fields(...)` should call the shared builder after validating the existing raw safe dictionaries. Only the reduced dataclass reaches Temporal.

### Task 3: GREEN — persist signature in real workflow snapshots

**Objective:** Make real Worker query/update snapshots expose only the safe signature.

**Files:**

- Modify: `prototypes/flowweaver_phase5b_temporal_poc/src/flowweaver_temporal_poc/workflows.py`

Implementation sketch:

1. Add `self._start_signature: dict[str, Any] = {}` in `__init__`.
2. In `run(...)`, after `validate_start_payload(payload)`, set `self._start_signature = start_signature_from_payload(payload)`.
3. Include `"start_signature": dict(self._start_signature)` in `_snapshot()`.
4. Do not log, send, perform IO, start services, or add side effects.

### Task 4: GREEN — compare safe signature in duplicate-start facade

**Objective:** Make duplicate-start parity use the workflow's safe signature, not only counts.

**Files:**

- Modify: `prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/runtime_client.py`

Implementation sketch:

1. Import `start_signature_from_payload` inside duplicate-start comparison.
2. Extend `_snapshot_matches_start_payload(...)` so it requires:
   - existing Phase 5H observable field checks;
   - `snapshot["start_signature"] == start_signature_from_payload(payload)`.
3. Continue returning safe `running` for matching active duplicate starts.
4. Continue returning safe `invalid_start_payload` for mismatch.
5. Do not return raw exception strings or workflow IDs in error results.

### Task 5: GREEN — keep fake reconciliation runtime schema-compatible

**Objective:** Preserve fake/real snapshot parity.

**Files:**

- Modify: `prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/reconciliation_harness.py`

Implementation sketch:

1. Add `"start_signature": start_signature_from_payload(payload)` to `_snapshot_from_payload(...)`.
2. Update `_payload_signature(...)` to use the reduced payload fields plus start signature; do not reintroduce raw policy into fake runtime state.
3. Add tests asserting fake and real snapshots expose the same safe signature for the same start payload.

### Task 6: Update existing tests for reduced start payload

**Objective:** Keep earlier Phase 5B/5C/5G tests meaningful under the reduced dataclass.

**Files:**

- Modify direct `RuntimeStartPayload(...)` construction in prototype tests to use the new builder or reduced digest fields.
- Keep publication dictionaries unchanged unless a test is specifically validating what reaches Temporal.

Rules:

1. Do not weaken existing validation assertions.
2. If a test asserts raw `claim_check_policy` in the Gateway publication, it may remain there.
3. If a test asserts Temporal payload/history/tool snapshot output, it must expect reduced digests only.

### Task 7: Phase 5I boundary gate

**Objective:** Prove this branch did not expand into production surfaces.

Gate all unstaged, staged, untracked, and committed `merge-base..HEAD` changed files.

Allowed changed files are exactly the planned files above. If the Phase 5H test-only adjustment becomes necessary, include it explicitly and document why.

Forbidden added-line markers:

```text
Gateway/platform imports or path edits
run_agent/model_tools/toolsets/tools/hermes_cli edits
Client.connect or connect_local_temporal outside existing approved facade paths
WorkflowEnvironment/Worker outside integration tests
Docker/systemctl/daemon/subprocess/socket/listener startup
config.yaml writes or Path.write_* in runtime source
eval/exec/importlib/__import__ dynamic bypasses
@workflow.signal / .signal( / signal_with_start
print/logger/logging/raw exception interpolation in changed runtime source
```

### Task 8: Focused verification

Run after GREEN:

```bash
# New Phase 5I integration proof
TZ=UTC LANG=C.UTF-8 LC_ALL=C.UTF-8 PYTHONHASHSEED=0 \
  /home/ubuntu/.hermes/hermes-agent/venv/bin/python -m pytest -o addopts= -n 4 \
  tests/integration/test_flowweaver_phase5i_start_signature_parity.py -q

# Temporal integration regression
TZ=UTC LANG=C.UTF-8 LC_ALL=C.UTF-8 PYTHONHASHSEED=0 \
  /home/ubuntu/.hermes/hermes-agent/venv/bin/python -m pytest -o addopts= -n 4 \
  tests/integration/test_flowweaver_phase5i_start_signature_parity.py \
  tests/integration/test_flowweaver_phase5c_runtime_client_temporal.py \
  tests/integration/test_flowweaver_phase5b_temporal_workflow.py \
  -q

# Prototype contracts/reconciliation
scripts/run_tests.sh \
  tests/prototypes/test_flowweaver_phase5i_start_signature_contract.py \
  tests/prototypes/test_flowweaver_phase5g_delivery_cardinality.py \
  tests/prototypes/test_flowweaver_phase5f_local_runtime_reconciliation.py \
  tests/prototypes/test_flowweaver_phase5e_local_publish_adapter.py \
  tests/prototypes/test_flowweaver_phase5c_runtime_client_contract.py \
  tests/prototypes/test_flowweaver_phase5c_tool_adapter.py \
  tests/prototypes/test_flowweaver_phase5b_temporal_payloads.py \
  -q
```

If the expanded prototype command repeats the pre-code optional Temporal import-order failure, isolate the affected selector, rerun it alone, and document whether it is verifier ordering or a new Phase 5I regression. Do not claim the expanded gate green until the corrected command set passes.

### Task 9: Syntax/lint/static/security gates

Run:

```bash
python -m py_compile \
  prototypes/flowweaver_phase5b_temporal_poc/src/flowweaver_temporal_poc/payloads.py \
  prototypes/flowweaver_phase5b_temporal_poc/src/flowweaver_temporal_poc/workflows.py \
  prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/contracts.py \
  prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/runtime_client.py \
  prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/reconciliation_harness.py \
  tests/integration/test_flowweaver_phase5i_start_signature_parity.py \
  tests/prototypes/test_flowweaver_phase5i_start_signature_contract.py
python -m ruff check \
  prototypes/flowweaver_phase5b_temporal_poc/src/flowweaver_temporal_poc/payloads.py \
  prototypes/flowweaver_phase5b_temporal_poc/src/flowweaver_temporal_poc/workflows.py \
  prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/contracts.py \
  prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/runtime_client.py \
  prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/reconciliation_harness.py \
  tests/integration/test_flowweaver_phase5i_start_signature_parity.py \
  tests/prototypes/test_flowweaver_phase5i_start_signature_contract.py
git diff --check
```

Custom gates:

1. Changed-file allowlist across unstaged, staged, untracked, and committed surfaces.
2. Secret-shaped added-line scan with synthetic strings split where necessary.
3. No production Gateway/platform/tool/global registry/config writes.
4. No base dependency change for `temporalio`.
5. No raw private/platform IDs or credential-shaped values in returned results, snapshots, logs, or history fixtures.
6. Raw Temporal history scan for Phase 5I forbidden start-policy markers.
7. No raw exception text interpolation in changed runtime source.
8. No payload-carrying Signals.

### Task 10: Independent reviews and PR

After green gates:

1. Run independent spec compliance review.
2. Run independent security/low-intrusion review.
3. Fix blockers with RED tests first.
4. Rerun focused gates after any fix.
5. Update this dev log with review and final verification evidence.
6. Rerun doc/static gates after doc updates.
7. Commit, push the Phase 5I branch, and open a PR against `feature/sachima-channel`.
8. Verify PR base/head/commit/checks.

## Acceptance Criteria

Phase 5I is complete only if:

1. Temporal workflow start input/history no longer contains raw start-policy fields or forbidden-material names; raw serialized history bytes are scanned.
2. A real local Temporal Worker rejects a duplicate start with the same workflow ID/counts/slots but a different safe idempotency key as `invalid_start_payload`.
3. Matching duplicate starts still return safe `running` and replay reconciliation still produces duplicate ACK statuses without extra state mutation.
4. Query/update snapshots include only the safe start-signature shape, not raw start payloads or raw claim-check policy material.
5. Fake runtime snapshots and real runtime snapshots expose compatible safe signatures through the Phase 5C sanitizer.
6. No production Gateway, platform adapter, tool registry, global config, base dependency, Docker, daemon, or service lifecycle code is touched.
7. All focused tests, syntax/lint gates, diff checks, custom safety gates, and independent implementation reviews pass.

## Handoff

This revised plan includes the independent review blockers: the test naming/coverage gaps and the Temporal history raw-policy leak. Under the user's Phase 5I execution approval, implementation may proceed after this revised plan/dev log pass doc gates and blocker-only re-review.
