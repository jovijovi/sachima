# FlowWeaver Phase 5A Durable Runtime Ingress Contract Implementation Plan

> **For Hermes:** User explicitly approved entering Phase 5A. Implement with strict TDD and keep the phase pure/local: no Temporal import, no runtime wiring, no persistence, no Gateway restart.

**Goal:** Add a pure in-memory runtime ingress contract helper that validates already-safe Phase 4F/4G/4H outputs and produces a narrow versioned envelope a future durable runtime may consume.

**Architecture:** Phase 5A creates `gateway/flowweaver_runtime_contract.py`, a contract-only helper. It consumes only the Phase 4F shadow consumer descriptor, Phase 4F replay corpus, Phase 4G mock durable projection, and optional Phase 4H dry-run summary. It returns safe metadata only: verdicts, versions, counts, allowed runtime event names, claim-check-reference rules, idempotency strategy, checks, and `side_effects: []`. It does not read raw snapshots/captures/agent results, does not import Temporal, and does not wire Gateway runtime behavior.

**Tech Stack:** Python, pytest, existing FlowWeaver Gateway helper modules, existing fake-agent Gateway lifecycle tests.

---

## Current Context / Evidence

Timestamp: 2026-05-05 12:21:44 CST +0800

Branch/worktree:

```text
repo: /home/ubuntu/workspace/hermes/repo/sachima
worktree: /home/ubuntu/workspace/hermes/worktrees/sachima/feat-flowweaver-phase5a-durable-runtime-ingress-contract
branch: feat/flowweaver-phase5a-durable-runtime-ingress-contract
base: origin/feature/sachima-channel @ a3227b4b68f6fe289249fdf01a6708089836009f
open PRs before branching: []
```

Baseline verification in the Phase 5A worktree:

```bash
scripts/run_tests.sh \
  tests/gateway/test_flowweaver_shadow_dry_run.py \
  tests/gateway/test_flowweaver_mock_durable_consumer.py \
  tests/gateway/test_flowweaver_shadow_tap.py \
  tests/gateway/test_flowweaver_contract_adapter.py \
  tests/gateway/test_delivery_state.py \
  tests/gateway/test_run_progress_topics.py \
  tests/gateway/test_rich_weather_delivery.py \
  -q
```

Observed:

```text
142 passed in 18.38s
```

Authoritative upstream gate:

```text
docs/plans/2026-05-05-flowweaver-phase5-architecture-gate.md
```

Phase 5A approved input surfaces:

```text
gateway.flowweaver_shadow.describe_flowweaver_shadow_consumer_contract()
gateway.flowweaver_shadow.replay_flowweaver_shadow_corpus(...)
gateway.flowweaver_mock_durable.consume_flowweaver_shadow_corpus_as_mock_durable_state(...)
gateway.flowweaver_shadow_dry_run.run_flowweaver_gateway_shadow_dry_run(...)
```

---

## Non-Goals / Hard Boundaries

Phase 5A must not do any of this:

```text
no Temporal imports
no temporalio dependency
no Temporal client / workflow / worker / task queue
no Docker
no daemon or service startup
no Gateway restart
no live Gateway runtime wiring
no platform adapter changes
no public flowweaver.v0 schema mutation
no run_agent.py changes
no model_tools.py changes
no toolsets.py changes
no cli.py / hermes_cli changes
no gateway/run.py changes
no sends / edits / renders / persistence / logging from the runtime contract helper
no raw snapshot/capture/full agent_result in accepted or rejected output
no raw command/stdout/stderr/card JSON/media bytes or paths/platform payloads/delivery ACK payloads
no platform/chat/user/message IDs or credential-shaped values
no remote branch deletion
```

Allowed implementation paths:

```text
docs/plans/2026-05-05-flowweaver-phase5a-durable-runtime-ingress-contract.md
docs/dev_log/2026-05-05-flowweaver-phase5a-durable-runtime-ingress-contract.md
gateway/flowweaver_runtime_contract.py
tests/gateway/test_flowweaver_runtime_contract.py
```

---

## Design: Runtime Ingress Contract Helper

Create:

```text
gateway/flowweaver_runtime_contract.py
```

Planned public surface:

```python
FLOWWEAVER_RUNTIME_CONTRACT_TYPE = "flowweaver.gateway.runtime_ingress_contract.v0"
FLOWWEAVER_RUNTIME_ENVELOPE_TYPE = "flowweaver.gateway.runtime_ingress_envelope.v0"
FLOWWEAVER_RUNTIME_ACCEPTED = "accepted"
FLOWWEAVER_RUNTIME_REJECTED = "rejected"
FLOWWEAVER_RUNTIME_MODEL_VERSION = "flowweaver.runtime.v0"

def describe_flowweaver_runtime_ingress_contract() -> dict[str, object]: ...

def build_flowweaver_runtime_ingress_envelope(
    contract_descriptor: Mapping[str, object],
    replay_corpus: Mapping[str, object],
    mock_durable_projection: Mapping[str, object],
    dry_run_summary: Mapping[str, object] | None = None,
) -> dict[str, object]: ...
```

Accepted output shape:

```python
{
    "type": "flowweaver.gateway.runtime_ingress_envelope.v0",
    "verdict": "accepted",
    "reason": "ok",
    "contract_type": "flowweaver.gateway.runtime_ingress_contract.v0",
    "contract_version": "flowweaver.v0",
    "runtime_model_version": "flowweaver.runtime.v0",
    "source_contract_type": "flowweaver.gateway.shadow_consumer_contract.v0",
    "source_corpus_type": "flowweaver.gateway.shadow_replay_corpus.v0",
    "source_mock_durable_type": "flowweaver.gateway.mock_durable_consumer.v0",
    "source_dry_run_type": "flowweaver.gateway.shadow_dry_run.v0" | None,
    "entry_count": 1,
    "record_counts": {"transactions": 1, "intents": 1, "artifacts": 1, "deliveries": 1},
    "idempotency": {
        "strategy": "synthetic_index_v0",
        "transaction_key": "runtime_tx_replay_corpus",
        "intent_key_prefix": "runtime_intent_",
        "artifact_key_prefix": "runtime_artifact_",
        "delivery_key_prefix": "runtime_delivery_",
    },
    "allowed_runtime_events": [
        "start_transaction",
        "record_operation",
        "publish_artifact",
        "plan_delivery",
        "record_delivery_ack",
        "approve_intent",
        "reject_intent",
        "cancel_transaction",
        "resume_after_user_input",
    ],
    "claim_check_policy": {
        "mode": "references_only",
        "allowed_reference_fields": ["ref", "kind", "count", "size", "checksum_hint"],
        "forbidden_material": [...raw material names...],
    },
    "checks": {
        "runtime_contract_valid": True,
        "source_contract_valid": True,
        "replay_corpus_passed": True,
        "mock_durable_accepted": True,
        "dry_run_summary_valid": True,
        "record_counts_match_entries": True,
        "payloads_absent": True,
        "claim_check_references_only": True,
        "side_effects_absent": True,
    },
    "side_effects": [],
}
```

Rejected output shape must be closed and narrow:

```python
{
    "type": "flowweaver.gateway.runtime_ingress_envelope.v0",
    "verdict": "rejected",
    "reason": "invalid_contract" | "invalid_corpus" | "corpus_not_passed" | "mock_durable_rejected" | "invalid_dry_run",
    "contract_type": None,
    "contract_version": None,
    "runtime_model_version": "flowweaver.runtime.v0",
    "source_contract_type": None,
    "source_corpus_type": None,
    "source_mock_durable_type": None,
    "source_dry_run_type": None,
    "entry_count": 0,
    "record_counts": {"transactions": 0, "intents": 0, "artifacts": 0, "deliveries": 0},
    "idempotency": None,
    "allowed_runtime_events": [],
    "claim_check_policy": {...reference-only policy...},
    "checks": {...safe booleans...},
    "side_effects": [],
}
```

Rejection must not echo attacker-controlled values.

---

## TDD Task Plan

### Task 0: Persist plan and dev log

**Objective:** Record Phase 5A context, approved scope, boundaries, and verification plan.

**Files:**

- Create: `docs/plans/2026-05-05-flowweaver-phase5a-durable-runtime-ingress-contract.md`
- Create: `docs/dev_log/2026-05-05-flowweaver-phase5a-durable-runtime-ingress-contract.md`

**Verification:**

```bash
git check-ignore -v \
  docs/plans/2026-05-05-flowweaver-phase5a-durable-runtime-ingress-contract.md \
  docs/dev_log/2026-05-05-flowweaver-phase5a-durable-runtime-ingress-contract.md \
  gateway/flowweaver_runtime_contract.py \
  tests/gateway/test_flowweaver_runtime_contract.py || true
git add -N docs/plans/2026-05-05-flowweaver-phase5a-durable-runtime-ingress-contract.md docs/dev_log/2026-05-05-flowweaver-phase5a-durable-runtime-ingress-contract.md
git diff --check -- docs/plans/2026-05-05-flowweaver-phase5a-durable-runtime-ingress-contract.md docs/dev_log/2026-05-05-flowweaver-phase5a-durable-runtime-ingress-contract.md
```

### Task 1: RED — runtime contract helper absent

**Objective:** Define the descriptor and accepted envelope behavior before implementation.

**Files:**

- Create: `tests/gateway/test_flowweaver_runtime_contract.py`

**Tests:**

```text
test_runtime_ingress_contract_describes_allowed_inputs_and_forbidden_side_effects
test_runtime_ingress_envelope_accepts_descriptor_corpus_mock_projection_and_dry_run_summary
test_runtime_ingress_envelope_projects_counts_events_and_claim_check_requirements_only
```

**Expected RED:**

```text
ModuleNotFoundError: No module named 'gateway.flowweaver_runtime_contract'
```

### Task 2: GREEN — minimal pure helper

**Objective:** Add the smallest exact-shape helper that accepts safe Phase 4F/4G/4H outputs.

**Files:**

- Create: `gateway/flowweaver_runtime_contract.py`

**Rules:**

1. Exact plain dict validation for envelopes.
2. Output derives only from safe types, verdicts, versions, counts, fixed event names, and fixed claim-check policy.
3. No raw records in accepted output beyond counts/idempotency strategy.
4. No Temporal import or runtime side effects.

### Task 3: RED/GREEN — rejection and no-leak hardening

**Objective:** Reject unsafe or hostile inputs without echoing values.

**Tests:**

```text
test_runtime_ingress_rejects_raw_snapshot_capture_or_agent_result_without_echoing_values
test_runtime_ingress_rejects_temporal_client_like_objects
test_runtime_ingress_rejects_platform_ack_payloads_and_private_ids
test_runtime_ingress_rejects_hostile_mapping_and_mutating_keys
test_runtime_ingress_rejects_post_validation_reread_attacks
test_runtime_ingress_output_omits_raw_command_stdout_card_json_and_secrets
test_runtime_ingress_side_effects_are_always_empty
```

### Task 4: Focused lifecycle regression without runtime wiring

**Objective:** Re-run existing Gateway shadow/dry-run lifecycle regressions beside the new runtime contract tests to prove Phase 5A did not change Gateway behavior.

**Files:**

- No additional implementation files.
- Existing `tests/gateway/test_run_progress_topics.py` tests may be selected in the focused gate, but the file is not modified in this phase.

**Test:**

```text
existing FlowWeaver shadow/dry-run lifecycle tests in tests/gateway/test_run_progress_topics.py
```

No helper import is added to Gateway runtime or platform adapter code.

### Task 5: Full focused gate, scans, and independent review

**Commands:**

```bash
scripts/run_tests.sh \
  tests/gateway/test_flowweaver_runtime_contract.py \
  tests/gateway/test_flowweaver_shadow_dry_run.py \
  tests/gateway/test_flowweaver_mock_durable_consumer.py \
  tests/gateway/test_flowweaver_shadow_tap.py \
  tests/gateway/test_flowweaver_contract_adapter.py \
  tests/gateway/test_delivery_state.py \
  tests/gateway/test_run_progress_topics.py \
  tests/gateway/test_rich_weather_delivery.py \
  -q
python -m py_compile \
  gateway/flowweaver_runtime_contract.py \
  gateway/flowweaver_shadow_dry_run.py \
  gateway/flowweaver_mock_durable.py \
  gateway/flowweaver_shadow.py \
  tests/gateway/test_flowweaver_runtime_contract.py \
  tests/gateway/test_flowweaver_shadow_dry_run.py \
  tests/gateway/test_flowweaver_mock_durable_consumer.py \
  tests/gateway/test_run_progress_topics.py
git diff --check
```

Additional scans:

```text
changed-file allowlist scan
forbidden runtime/path scan
Temporal import/client/workflow/worker scan
send/edit/render/persist/log side-effect scan
sensitive/private-id added-line scan
final candidate leak scan over runtime contract outputs/tests/docs
```

Independent reviews:

```text
spec / low-intrusion review
security / no-leak review
Temporal boundary review
```

---

## Approval Gate

User approved starting Phase 5A in Feishu with: `OK，先做5A阶段`.

Implementation may proceed in this branch with strict TDD and the hard boundaries above.
