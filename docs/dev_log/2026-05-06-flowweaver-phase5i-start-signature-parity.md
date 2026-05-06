# FlowWeaver Phase 5I — Start Signature Parity Dev Log

Timestamp: 2026-05-06 15:46:31 CST +0800

## Scope

User approved Phase 5I implementation after Phase 5H / PR #34 merge.

Phase 5I target:

```text
Persist a safe start-signature summary in the local Temporal POC snapshot and use it during real-worker duplicate-start recovery, so duplicate starts with matching observable counts but mismatched safe start identity are rejected deterministically.
```

This phase remains prototype-only/default-off. It must not touch production Gateway wiring, platform adapters, tool registry, global config, base dependencies, Docker/daemon/service lifecycle, or remote branch deletion.

## Out of scope

```text
gateway/run.py changes
gateway/platforms/** changes
run_agent.py changes
model_tools.py changes
toolsets.py changes
tools/** changes
hermes_cli/** changes
production Hermes tool registration
production Gateway -> Temporal wiring
Docker / Temporal CLI / daemon / external Temporal service startup
~/.hermes/config.yaml writes
base dependency changes that install temporalio outside optional extras
payload-carrying Signals
remote branch deletion
PR merge
```

## Baseline State

```text
canonical repo: /home/ubuntu/workspace/hermes/repo/sachima
canonical branch: feature/sachima-channel
canonical HEAD: f474811052fd901a83f5b318c395e5f33478c9d3
origin/feature/sachima-channel: f474811052fd901a83f5b318c395e5f33478c9d3
Phase 5I worktree: /home/ubuntu/workspace/hermes/worktrees/sachima/feat-flowweaver-phase5i-start-signature-parity
Phase 5I branch: feat/flowweaver-phase5i-start-signature-parity
```

Pre-existing canonical untracked items are not part of this phase:

```text
.hermes/
docs/plans/2026-04-24-sachima-channel.md
docs/superpowers/
```

## Context Inspected

```text
prototypes/flowweaver_phase5b_temporal_poc/src/flowweaver_temporal_poc/payloads.py
prototypes/flowweaver_phase5b_temporal_poc/src/flowweaver_temporal_poc/workflows.py
prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/contracts.py
prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/runtime_client.py
prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/reconciliation_harness.py
tests/integration/test_flowweaver_phase5h_local_temporal_worker_reconciliation.py
```

Relevant Phase 5H fact:

```text
Phase 5H deliberately limited duplicate-start mismatch detection to workflow-observable safe fields represented in the current snapshot. Full hidden start-signature persistence was explicitly deferred.
```

## Baseline Verification

Temporal integration baseline before Phase 5I changes:

```text
TZ=UTC LANG=C.UTF-8 LC_ALL=C.UTF-8 PYTHONHASHSEED=0 \
  /home/ubuntu/.hermes/hermes-agent/venv/bin/python -m pytest -o addopts= -n 4 \
  tests/integration/test_flowweaver_phase5h_local_temporal_worker_reconciliation.py \
  tests/integration/test_flowweaver_phase5c_runtime_client_temporal.py \
  tests/integration/test_flowweaver_phase5b_temporal_workflow.py \
  -q

18 passed in 1.29s
```

Expanded prototype baseline before Phase 5I changes:

```text
scripts/run_tests.sh \
  tests/prototypes/test_flowweaver_phase5g_delivery_cardinality.py \
  tests/prototypes/test_flowweaver_phase5f_local_runtime_reconciliation.py \
  tests/prototypes/test_flowweaver_phase5e_local_publish_adapter.py \
  tests/prototypes/test_flowweaver_phase5c_runtime_client_contract.py \
  tests/prototypes/test_flowweaver_phase5c_tool_adapter.py \
  tests/prototypes/test_flowweaver_phase5b_temporal_payloads.py \
  -q

48 passed, 1 failed
```

Failure was isolated to:

```text
tests/prototypes/test_flowweaver_phase5b_temporal_payloads.py::test_client_helper_requires_explicit_address_and_workflow_id
AttributeError: module 'temporalio' has no attribute 'converter'
```

Isolation evidence:

```text
scripts/run_tests.sh tests/prototypes/test_flowweaver_phase5b_temporal_payloads.py::test_client_helper_requires_explicit_address_and_workflow_id -q
# 1 passed in 0.52s

TZ=UTC LANG=C.UTF-8 LC_ALL=C.UTF-8 PYTHONHASHSEED=0 \
  /home/ubuntu/.hermes/hermes-agent/venv/bin/python -m pytest -o addopts= \
  tests/prototypes/test_flowweaver_phase5b_temporal_payloads.py::test_client_helper_requires_explicit_address_and_workflow_id -q
# 1 passed in 0.17s
```

Conclusion: pre-code expanded prototype chain has an environment/order-sensitive optional Temporal import issue. It is not caused by Phase 5I changes. Final verification must isolate and rerun corrected selectors instead of calling the combined expanded gate green by accident.

## Plan

Plan saved at:

```text
docs/plans/2026-05-06-flowweaver-phase5i-start-signature-parity.md
```

Planned implementation files:

```text
prototypes/flowweaver_phase5b_temporal_poc/src/flowweaver_temporal_poc/payloads.py
prototypes/flowweaver_phase5b_temporal_poc/src/flowweaver_temporal_poc/workflows.py
prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/contracts.py
prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/runtime_client.py
prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/reconciliation_harness.py
tests/integration/test_flowweaver_phase5i_start_signature_parity.py
tests/prototypes/test_flowweaver_phase5i_start_signature_contract.py
```

## Plan Review

Initial independent plan review results:

```text
Spec/TDD reviewer: FAIL
- Digest-change test was misnamed because idempotency is stored directly while only event contract and policy are digested.
- Matching duplicate regression was not explicit enough.
- Fake/real start_signature snapshot parity needed an explicit assertion.

Security/low-intrusion reviewer: FAIL
- Current Temporal history can contain raw start-policy material because RuntimeStartPayload includes raw allowed_runtime_events and claim_check_policy.
- Plan needed an explicit raw serialized history scan after start/duplicate/cancel.
```

Plan revisions made after review:

```text
- Phase 5I scope narrowed/clarified to include Temporal start payload reduction before start_workflow.
- RuntimeStartPayload planned shape now contains only transaction_id, idempotency_key, entry_count, record_counts, event_contract_digest, and claim_policy_digest.
- Added RED history leak test for rendered history and serialized event bytes.
- Added matching duplicate regression.
- Added fake/real safe start_signature parity assertion.
- Added existing-test update task for direct RuntimeStartPayload constructors.
```

## Execution Log

Blocker-only plan re-review:

```text
Spec/TDD re-review: PASS
Security/low-intrusion re-review: PASS
```

Phase 5I RED tests added:

```text
tests/integration/test_flowweaver_phase5i_start_signature_parity.py
tests/prototypes/test_flowweaver_phase5i_start_signature_contract.py
```

RED verification before implementation:

```text
TZ=UTC LANG=C.UTF-8 LC_ALL=C.UTF-8 PYTHONHASHSEED=0 \
  /home/ubuntu/.hermes/hermes-agent/venv/bin/python -m pytest -o addopts= -n 4 \
  tests/integration/test_flowweaver_phase5i_start_signature_parity.py -q
# exit 1
# Expected failures: Temporal history still exposed raw allowed_runtime_events material, and duplicate idempotency/signature mismatch was accepted.

scripts/run_tests.sh tests/prototypes/test_flowweaver_phase5i_start_signature_contract.py -q
# exit 1
# Expected failure: reduced start-payload/signature API did not exist yet.
```

GREEN implementation summary:

```text
- RuntimeStartPayload reduced to transaction_id, idempotency_key, entry_count, record_counts, event_contract_digest, claim_policy_digest.
- build_runtime_start_payload() now converts raw event/policy inputs into deterministic runtime_sig_ digests.
- Workflow start persists safe start_signature and query snapshots expose only the safe signature.
- Runtime facade duplicate active workflow recovery compares snapshot start_signature with start_signature_from_payload(payload).
- Local reconciliation harness safe/fake snapshots now carry start_signature parity.
```

Focused Phase 5I GREEN checks:

```text
TZ=UTC LANG=C.UTF-8 LC_ALL=C.UTF-8 PYTHONHASHSEED=0 \
  /home/ubuntu/.hermes/hermes-agent/venv/bin/python -m pytest -o addopts= -n 4 \
  tests/integration/test_flowweaver_phase5i_start_signature_parity.py -q
# 4 passed in 0.82s

scripts/run_tests.sh tests/prototypes/test_flowweaver_phase5i_start_signature_contract.py -q
# passed
```

Old regression adaptation:

```text
- Updated Phase 5B/5C/5E/5G tests and fixtures to use build_runtime_start_payload() or safe start_signature snapshots instead of direct old RuntimeStartPayload(raw allowed_runtime_events, raw claim_check_policy) construction.
- Updated Phase 5H/5I diff gates to keep production Gateway/platform/tool surfaces forbidden while allowing Phase 5I prototype/test/doc files.
- Fixed a test isolation issue by clearing the full temporalio.* module tree before asserting the general contract import remains Temporal-free; this prevents stale submodule state from breaking later optional Temporal imports.
```

Final focused/regression verification:

```text
TZ=UTC LANG=C.UTF-8 LC_ALL=C.UTF-8 PYTHONHASHSEED=0 \
  /home/ubuntu/.hermes/hermes-agent/venv/bin/python -m pytest -o addopts= -n 4 \
  tests/integration/test_flowweaver_phase5i_start_signature_parity.py \
  tests/integration/test_flowweaver_phase5h_local_temporal_worker_reconciliation.py \
  tests/integration/test_flowweaver_phase5c_runtime_client_temporal.py \
  tests/integration/test_flowweaver_phase5b_temporal_workflow.py \
  -q
# 23 passed in 1.42s

scripts/run_tests.sh \
  tests/prototypes/test_flowweaver_phase5b_temporal_payloads.py \
  tests/prototypes/test_flowweaver_phase5c_runtime_client_contract.py \
  tests/prototypes/test_flowweaver_phase5c_tool_adapter.py \
  tests/prototypes/test_flowweaver_phase5c_mcp_server_surface.py \
  tests/prototypes/test_flowweaver_phase5c_tool_surface.py \
  tests/prototypes/test_flowweaver_phase5e_local_publish_adapter.py \
  tests/prototypes/test_flowweaver_phase5e_variable_runtime_ids.py \
  tests/prototypes/test_flowweaver_phase5f_local_runtime_reconciliation.py \
  tests/prototypes/test_flowweaver_phase5g_delivery_cardinality.py \
  tests/prototypes/test_flowweaver_phase5i_start_signature_contract.py \
  -q
# 76 passed in 0.59s
```

Static/security gates:

```text
python -m py_compile relevant Phase 5I source/tests
# passed

python -m ruff check relevant Phase 5I source/tests
# All checks passed

git diff --check
# passed

custom security gates
# passed: no production Gateway/platform/tool surface changes, no base temporalio dependency leak, no payload-carrying Signals, no Docker/daemon/service lifecycle additions, no secret-like patterns, RuntimeStartPayload field set is reduced and safe, runtime_sig_ digests reject forged non-hex/raw-marker values.
```

Independent implementation review:

```text
Spec/TDD reviewer: FAIL
Security/low-intrusion reviewer: FAIL
Shared blocker: runtime_sig_ digest fields were validated only by generic prefix checks, so a forged public RuntimeStartPayload could carry marker-like strings such as runtime_sig_claim_check_policy into Temporal start history/snapshot surfaces.
```

Blocker RED tests added after review:

```text
scripts/run_tests.sh \
  tests/prototypes/test_flowweaver_phase5i_start_signature_contract.py::test_phase5i_validate_start_payload_rejects_forged_non_hex_or_raw_marker_digests \
  tests/prototypes/test_flowweaver_phase5i_start_signature_contract.py::test_phase5i_snapshot_sanitizer_rejects_forged_non_hex_or_raw_marker_digests \
  -q
# 10 failed as expected: forged runtime_sig_ values were accepted.

TZ=UTC LANG=C.UTF-8 LC_ALL=C.UTF-8 PYTHONHASHSEED=0 \
  /home/ubuntu/.hermes/hermes-agent/venv/bin/python -m pytest -o addopts= -n 4 \
  tests/integration/test_flowweaver_phase5i_start_signature_parity.py::test_phase5i_runtime_facade_rejects_forged_non_hex_start_signature_before_start \
  -q
# 1 failed as expected: forged payload started instead of raising invalid_start_payload.
```

Blocker fix:

```text
- Added validate_runtime_signature_digest() requiring exactly runtime_sig_ + 64 lowercase sha256 hex chars.
- validate_start_payload() now uses the strict digest validator for event_contract_digest and claim_policy_digest.
- sanitize_snapshot()/start_signature sanitizer now uses the same strict digest validator.
```

Blocker GREEN and refreshed gates:

```text
scripts/run_tests.sh \
  tests/prototypes/test_flowweaver_phase5i_start_signature_contract.py::test_phase5i_validate_start_payload_rejects_forged_non_hex_or_raw_marker_digests \
  tests/prototypes/test_flowweaver_phase5i_start_signature_contract.py::test_phase5i_snapshot_sanitizer_rejects_forged_non_hex_or_raw_marker_digests \
  -q
# 10 passed in 0.38s

TZ=UTC LANG=C.UTF-8 LC_ALL=C.UTF-8 PYTHONHASHSEED=0 \
  /home/ubuntu/.hermes/hermes-agent/venv/bin/python -m pytest -o addopts= -n 4 \
  tests/integration/test_flowweaver_phase5i_start_signature_parity.py::test_phase5i_runtime_facade_rejects_forged_non_hex_start_signature_before_start \
  -q
# 1 passed in 0.76s

TZ=UTC LANG=C.UTF-8 LC_ALL=C.UTF-8 PYTHONHASHSEED=0 \
  /home/ubuntu/.hermes/hermes-agent/venv/bin/python -m pytest -o addopts= -n 4 \
  tests/integration/test_flowweaver_phase5i_start_signature_parity.py \
  tests/integration/test_flowweaver_phase5h_local_temporal_worker_reconciliation.py \
  tests/integration/test_flowweaver_phase5c_runtime_client_temporal.py \
  tests/integration/test_flowweaver_phase5b_temporal_workflow.py \
  -q
# 23 passed in 1.42s

scripts/run_tests.sh \
  tests/prototypes/test_flowweaver_phase5b_temporal_payloads.py \
  tests/prototypes/test_flowweaver_phase5c_runtime_client_contract.py \
  tests/prototypes/test_flowweaver_phase5c_tool_adapter.py \
  tests/prototypes/test_flowweaver_phase5c_mcp_server_surface.py \
  tests/prototypes/test_flowweaver_phase5c_tool_surface.py \
  tests/prototypes/test_flowweaver_phase5e_local_publish_adapter.py \
  tests/prototypes/test_flowweaver_phase5e_variable_runtime_ids.py \
  tests/prototypes/test_flowweaver_phase5f_local_runtime_reconciliation.py \
  tests/prototypes/test_flowweaver_phase5g_delivery_cardinality.py \
  tests/prototypes/test_flowweaver_phase5i_start_signature_contract.py \
  -q
# 76 passed in 0.59s

python -m py_compile relevant Phase 5I source/tests
python -m ruff check relevant Phase 5I source/tests
# All checks passed

git diff --check
custom security gates
# passed
```

Second independent security review blocker:

```text
Security/low-intrusion re-review: FAIL
Blocker: synthetic IDs accepted Phase 5I raw policy markers. Values such as runtime_tx_claim_check_policy, runtime_event_allowed_runtime_events, or snapshot start_signature.idempotency_key containing forbidden_material could still pass prefix/charset/private-marker checks and enter Temporal history-safe payload/snapshot surfaces.
```

Codex-assisted root cause and TDD fix:

```text
Root cause: _synthetic_id() existed in both Phase 5B payload validation and Phase 5C runtime contracts, but neither validator rejected Phase 5I policy marker substrings.
RED tests added before implementation:
- validate_start_payload rejects forged transaction_id/idempotency_key containing allowed_runtime_events, claim_check_policy, or forbidden_material.
- validate_workflow_id rejects forged workflow_id containing those markers.
- sanitize_snapshot rejects forged start_signature.idempotency_key containing those markers.
- FlowWeaverRuntimeClient facade rejects forged synthetic IDs before calling start_workflow.

RED evidence from Codex run:
- Prototype marker tests: 12 failed as expected with DID NOT RAISE.
- Facade guard test: failed as expected by reaching the StartForbiddenTemporalClient/start_workflow_called sentinel before the fix.

Fix:
- Added allowed_runtime_events, claim_check_policy, and forbidden_material to Phase 5B synthetic-ID forbidden substring validation.
- Added a Phase 5C _SYNTHETIC_ID_FORBIDDEN_SUBSTRINGS tuple with the same policy markers for runtime contract/snapshot-facing synthetic IDs.
- Added policy markers to runtime contract rendered-result defense.
```

Codex fix independent verification:

```text
scripts/run_tests.sh tests/prototypes/test_flowweaver_phase5i_start_signature_contract.py -q
# 28 passed in 0.38s

TZ=UTC LANG=C.UTF-8 LC_ALL=C.UTF-8 PYTHONHASHSEED=0 \
  /home/ubuntu/.hermes/hermes-agent/venv/bin/python -m pytest -o addopts= -n 4 \
  tests/integration/test_flowweaver_phase5i_start_signature_parity.py -q
# 6 passed in 0.84s

TZ=UTC LANG=C.UTF-8 LC_ALL=C.UTF-8 PYTHONHASHSEED=0 \
  /home/ubuntu/.hermes/hermes-agent/venv/bin/python -m pytest -o addopts= -n 4 \
  tests/integration/test_flowweaver_phase5i_start_signature_parity.py \
  tests/integration/test_flowweaver_phase5h_local_temporal_worker_reconciliation.py \
  tests/integration/test_flowweaver_phase5c_runtime_client_temporal.py \
  tests/integration/test_flowweaver_phase5b_temporal_workflow.py \
  -q
# 24 passed in 1.33s

scripts/run_tests.sh \
  tests/prototypes/test_flowweaver_phase5b_temporal_payloads.py \
  tests/prototypes/test_flowweaver_phase5c_runtime_client_contract.py \
  tests/prototypes/test_flowweaver_phase5c_tool_adapter.py \
  tests/prototypes/test_flowweaver_phase5c_mcp_server_surface.py \
  tests/prototypes/test_flowweaver_phase5c_tool_surface.py \
  tests/prototypes/test_flowweaver_phase5e_local_publish_adapter.py \
  tests/prototypes/test_flowweaver_phase5e_variable_runtime_ids.py \
  tests/prototypes/test_flowweaver_phase5f_local_runtime_reconciliation.py \
  tests/prototypes/test_flowweaver_phase5g_delivery_cardinality.py \
  tests/prototypes/test_flowweaver_phase5i_start_signature_contract.py \
  -q
# 88 passed in 0.60s

python -m py_compile relevant Phase 5I source/tests
python -m ruff check relevant Phase 5I source/tests
# All checks passed

git diff --check
custom security gates
# passed, including forged synthetic-ID marker rejection in validate_start_payload(), validate_workflow_id(), and sanitize_snapshot().
```

Final blocker-only implementation re-review:

```text
Security/low-intrusion re-review: PASS
- Reviewer probe confirmed validate_start_payload(), validate_workflow_id(), and sanitize_snapshot() reject allowed_runtime_events, claim_check_policy, and forbidden_material when embedded in Temporal-bound synthetic IDs.
- Valid IDs and strict runtime_sig_ + 64 lowercase hex digests still pass.
- Changed-file surface remains docs/prototypes/tests only; no production Gateway/platform/tool/global config/base dependency changes.

Spec/TDD/maintainability re-review: PASS
- Reviewer accepted the RED tests as meaningful and the StartForbiddenTemporalClient facade guard as the right fast pre-start validation proof.
- Implementation is minimal and no valid existing positive fixture IDs were found to be broken by the new exact policy-marker substring guard.
```
