# FlowWeaver Phase 4G Mock Durable Consumer Implementation Plan

> **For Hermes:** Execute implementation only after design approval. This document is the design handoff for Phase 4G; do not write implementation code until the user explicitly approves the execution gate.

**Goal:** Add a pure, in-memory mock durable consumer that validates the Phase 4F consumer descriptor and replay corpus can be projected into future durable `Transaction / Intent / Artifact / Delivery` record shapes without reading raw snapshots or changing Gateway behavior.

**Architecture:** Phase 4G introduces a narrow local helper module that consumes only the Phase 4F static descriptor and safe replay-corpus aggregate. It produces synthetic durable-state records derived from safe entry indexes, verdicts, and checks; it does not consume full snapshots, captures, platform payloads, card JSON, raw command/output, delivery ACKs, or platform identifiers. The helper remains default-off, in-memory, deterministic, read-only, no-send, no-edit, no-render, no-persist, no-log, and no-Temporal.

**Tech Stack:** Python, pytest, existing `gateway/flowweaver_shadow.py` Phase 4F descriptor/corpus helpers, new pure helper module under `gateway/`, new focused tests under `tests/gateway/`, existing Gateway lifecycle fake-agent regression style.

---

## Current Context / Evidence

Timestamp: 2026-05-04 23:15:41 CST +0800

Branch/worktree:

```text
repo: /home/ubuntu/workspace/hermes/repo/sachima
worktree: /home/ubuntu/workspace/hermes/worktrees/sachima/feat-flowweaver-phase4g-mock-durable-consumer
branch: feat/flowweaver-phase4g-mock-durable-consumer
base: origin/feature/sachima-channel @ dbb27c05a8628266056b702b7a53e97bb4ca3524
canonical before branching: feature/sachima-channel, 0 ahead / 0 behind
open PRs before branching: none
```

Baseline verification in the Phase 4G worktree:

```bash
scripts/run_tests.sh \
  tests/gateway/test_flowweaver_shadow_tap.py \
  tests/gateway/test_flowweaver_contract_adapter.py \
  tests/gateway/test_delivery_state.py \
  tests/gateway/test_run_progress_topics.py \
  tests/gateway/test_rich_weather_delivery.py \
  -q
```

Observed:

```text
108 passed in 14.94s
```

Relevant Phase 4F state inspected before this plan:

```text
gateway/flowweaver_shadow.py
  describe_flowweaver_shadow_consumer_contract()
  replay_flowweaver_shadow_corpus(agent_results, *, attempts=2)
  audit/replay/corpus outputs narrowed to verdict/reason/checks/side_effects plus safe refs only where explicitly allowed

tests/gateway/test_flowweaver_shadow_tap.py
  descriptor tests
  replay corpus tests
  hostile-input/no-mutation/no-leak tests

tests/gateway/fixtures/flowweaver_shadow_replay_corpus.json
  scenario-only synthetic corpus definitions

tests/gateway/test_run_progress_topics.py
  fake-agent Gateway lifecycle regressions proving corpus replay has no visible sends/edits

gateway/flowweaver_contract.py
  existing sanitized `flowweaver.handle.v0` snapshot shape; not a Phase 4G input surface
```

---

## Non-Goals / Hard Boundaries

Phase 4G must not do any of this:

```text
no Temporal integration
no Docker
no daemon or service startup
no Gateway restart
no live IM behavior change by default
no public flowweaver.v0 schema mutation
no run_agent.py changes
no model_tools.py changes
no toolsets.py changes
no cli.py / hermes_cli changes
no gateway/run.py changes unless the design is explicitly reopened
no gateway/platforms/* changes
no Feishu SDK calls
no sends / edits / renders / persistence / logging from the mock consumer
no remote branch deletion
```

Allowed implementation paths planned after approval:

```text
docs/plans/2026-05-04-flowweaver-phase4g-mock-durable-consumer.md
docs/dev_log/2026-05-04-flowweaver-phase4g-mock-durable-consumer.md
gateway/flowweaver_mock_durable.py
tests/gateway/test_flowweaver_mock_durable_consumer.py
tests/gateway/test_run_progress_topics.py
```

Existing Phase 4F files may be imported by tests, but should not need production edits:

```text
gateway/flowweaver_shadow.py
tests/gateway/test_flowweaver_shadow_tap.py
tests/gateway/fixtures/flowweaver_shadow_replay_corpus.json
```

If any implementation pressure appears to require `gateway/run.py`, `gateway/platforms/*`, `run_agent.py`, external storage, service startup, or Temporal, stop and redesign before writing code.

---

## Design: Mock Durable Consumer

Create a pure helper module:

```text
gateway/flowweaver_mock_durable.py
```

Planned public surface:

```python
FLOWWEAVER_MOCK_DURABLE_CONSUMER_TYPE = "flowweaver.gateway.mock_durable_consumer.v0"
FLOWWEAVER_MOCK_DURABLE_ACCEPTED = "accepted"
FLOWWEAVER_MOCK_DURABLE_REJECTED = "rejected"

consume_flowweaver_shadow_corpus_as_mock_durable_state(
    contract_descriptor: Mapping[str, Any],
    replay_corpus: Mapping[str, Any],
) -> dict[str, Any]
```

The exact naming can still be adjusted during RED test writing, but the helper must remain a pure projection from safe descriptor + safe corpus aggregate only.

### Input rules

Accepted input is only:

1. `describe_flowweaver_shadow_consumer_contract()` output.
2. `replay_flowweaver_shadow_corpus(...)` output.

Rejected input includes:

```text
full FlowWeaver snapshot mappings
shadow capture mappings
agent_result mappings
Gateway source/event objects
platform adapter objects
raw user/tool payload objects
failed/rejected corpus aggregates
hostile mappings that throw during read
any mapping that includes unexpected sensitive-looking raw fields
```

### Output shape

Expected safe projection shape:

```python
{
    "type": "flowweaver.gateway.mock_durable_consumer.v0",
    "verdict": "accepted",  # accepted | rejected
    "reason": "ok",
    "contract_type": "flowweaver.gateway.shadow_consumer_contract.v0",
    "contract_version": "flowweaver.v0",
    "corpus_type": "flowweaver.gateway.shadow_replay_corpus.v0",
    "corpus_verdict": "passed",
    "entry_count": 3,
    "records": {
        "transaction": {
            "record_id": "mock_tx_replay_corpus",
            "status": "succeeded",
            "entry_count": 3,
        },
        "intents": [
            {
                "intent_id": "mock_intent_0",
                "source_entry_index": 0,
                "status": "succeeded",
                "replay_verdict": "replayed",
            }
        ],
        "artifacts": [
            {
                "artifact_id": "mock_artifact_0",
                "intent_id": "mock_intent_0",
                "kind": "shadow_replay_verdict",
                "status": "available",
            }
        ],
        "deliveries": [
            {
                "delivery_id": "mock_delivery_0",
                "artifact_id": "mock_artifact_0",
                "surface": "mock_consumer",
                "status": "observed",
            }
        ],
    },
    "checks": {
        "contract_descriptor_valid": True,
        "corpus_valid": True,
        "corpus_passed": True,
        "record_counts_match_entries": True,
        "payloads_absent": True,
        "side_effects_absent": True,
    },
    "side_effects": [],
}
```

Important distinction: Phase 4G may use durable record labels such as `transaction`, `artifacts`, and `deliveries`, but those records must be synthetic mock durable records. They must not copy or expose the underlying FlowWeaver snapshot `transaction`, snapshot `artifacts`, snapshot `deliveries`, shadow `capture`, platform identifiers, message identifiers, delivery ACKs, raw output, card JSON, or credential-shaped strings.

### Rejection output shape

Rejected output must be closed and narrow:

```python
{
    "type": "flowweaver.gateway.mock_durable_consumer.v0",
    "verdict": "rejected",
    "reason": "invalid_contract",  # invalid_contract | invalid_corpus | corpus_not_passed
    "contract_type": None,
    "contract_version": None,
    "corpus_type": None,
    "corpus_verdict": None,
    "entry_count": 0,
    "records": {
        "transaction": None,
        "intents": [],
        "artifacts": [],
        "deliveries": [],
    },
    "checks": {
        "contract_descriptor_valid": False,
        "corpus_valid": False,
        "corpus_passed": False,
        "record_counts_match_entries": False,
        "payloads_absent": True,
        "side_effects_absent": True,
    },
    "side_effects": [],
}
```

Rejection output must not echo attacker-controlled values or unexpected fields.

---

## Safety Invariants

1. The mock consumer must be deterministic and side-effect-free.
2. It must not import or call Temporal, Docker, platform SDKs, Gateway runtime send/edit/render paths, persistence APIs, or logging APIs.
3. It must not read `FLOWWEAVER_SHADOW_SNAPSHOT_KEY`, `FLOWWEAVER_SHADOW_CAPTURE_KEY`, `agent_result`, `source`, `card_json`, `stdout`, `stderr`, raw command/output fields, platform/chat/user/message identifiers, or delivery ACK payloads.
4. It must not mutate descriptor or corpus inputs.
5. It must validate the descriptor type/version/keys and the corpus type/verdict/entry shape before projecting records.
6. It must reject failed/rejected corpus aggregates; Phase 4G is a durable-shape validation consumer, not a recovery workflow.
7. All IDs in the output must be synthetic deterministic IDs derived from entry index/count only, for example `mock_intent_0`.
8. `side_effects` must always be `[]`.
9. Gateway lifecycle regression must prove that running the mock consumer after a fake-agent response does not create visible `send` or `edit` calls.
10. Public `flowweaver.v0` schema remains unchanged.

---

## TDD Task Plan

### Task 0: Persist approved design plan and initial dev log

**Objective:** Record Phase 4G design, baseline, context, and approval gate before implementation.

**Files:**

- Create: `docs/plans/2026-05-04-flowweaver-phase4g-mock-durable-consumer.md`
- Create: `docs/dev_log/2026-05-04-flowweaver-phase4g-mock-durable-consumer.md`

**Verification:**

```bash
git check-ignore -v \
  docs/plans/2026-05-04-flowweaver-phase4g-mock-durable-consumer.md \
  docs/dev_log/2026-05-04-flowweaver-phase4g-mock-durable-consumer.md \
  gateway/flowweaver_mock_durable.py \
  tests/gateway/test_flowweaver_mock_durable_consumer.py || true
git diff --check
```

### Task 1: RED — mock durable consumer helper is absent

**Objective:** Define the accepted output shape before implementation.

**Files:**

- Create: `tests/gateway/test_flowweaver_mock_durable_consumer.py`

**Tests to add before implementation:**

```text
test_mock_durable_consumer_accepts_descriptor_and_passed_corpus
test_mock_durable_consumer_projects_synthetic_transaction_intent_artifact_delivery_records
```

**Expected RED:**

```text
ModuleNotFoundError: No module named 'gateway.flowweaver_mock_durable'
```

**RED command:**

```bash
scripts/run_tests.sh \
  tests/gateway/test_flowweaver_mock_durable_consumer.py::test_mock_durable_consumer_accepts_descriptor_and_passed_corpus \
  tests/gateway/test_flowweaver_mock_durable_consumer.py::test_mock_durable_consumer_projects_synthetic_transaction_intent_artifact_delivery_records \
  -q
```

### Task 2: GREEN — implement minimal pure projection

**Objective:** Add the smallest pure module that validates the descriptor/corpus envelope and builds synthetic records.

**Files:**

- Create: `gateway/flowweaver_mock_durable.py`

**Implementation rules:**

1. Import only safe constants from `gateway.flowweaver_shadow`.
2. Accept only mapping inputs.
3. Require descriptor type `flowweaver.gateway.shadow_consumer_contract.v0` and contract version `flowweaver.v0`.
4. Require corpus type `flowweaver.gateway.shadow_replay_corpus.v0`, verdict `passed`, reason `ok`, side effects `[]`, bounded entries, and per-entry verdict `replayed`.
5. Build synthetic deterministic records from entry indexes only.
6. Return no raw snapshot, capture, platform payload, message identifier, delivery ACK, or raw command/output material.
7. Mutate nothing.

**GREEN command:**

```bash
scripts/run_tests.sh tests/gateway/test_flowweaver_mock_durable_consumer.py -q
python -m py_compile gateway/flowweaver_mock_durable.py tests/gateway/test_flowweaver_mock_durable_consumer.py
```

### Task 3: RED/GREEN — rejection and no-leak hardening

**Objective:** Ensure the mock durable consumer fails closed for malformed or unsafe inputs without echoing hostile values.

**Files:**

- Modify: `tests/gateway/test_flowweaver_mock_durable_consumer.py`
- Modify: `gateway/flowweaver_mock_durable.py`

**Tests to add before implementation:**

```text
test_mock_durable_consumer_rejects_invalid_descriptor_without_echoing_values
test_mock_durable_consumer_rejects_failed_or_rejected_corpus
test_mock_durable_consumer_rejects_raw_snapshot_or_capture_inputs
test_mock_durable_consumer_does_not_mutate_inputs
test_mock_durable_consumer_output_omits_payload_ids_and_sensitive_shapes
```

**Expected RED examples:**

```text
assert projection["verdict"] == "rejected"
assert "snapshot" not in repr(projection)
```

**GREEN command:**

```bash
scripts/run_tests.sh tests/gateway/test_flowweaver_mock_durable_consumer.py -q
python -m py_compile gateway/flowweaver_mock_durable.py tests/gateway/test_flowweaver_mock_durable_consumer.py
```

### Task 4: RED/GREEN — corpus fixture integration

**Objective:** Prove the Phase 4F scenario-only replay corpus can feed the mock durable consumer through descriptor + corpus aggregate only.

**Files:**

- Modify: `tests/gateway/test_flowweaver_mock_durable_consumer.py`

**Test to add:**

```text
test_mock_durable_consumer_consumes_phase4f_fixture_through_safe_corpus_only
```

**Verification command:**

```bash
scripts/run_tests.sh tests/gateway/test_flowweaver_mock_durable_consumer.py -q
```

### Task 5: RED/GREEN — Gateway lifecycle regression

**Objective:** Verify the mock durable consumer can run after a fake-agent Gateway result without visible side effects.

**Files:**

- Modify: `tests/gateway/test_run_progress_topics.py`

**Test to add:**

```text
test_flowweaver_mock_durable_consumer_without_visible_side_effects
```

**Expected assertions:**

```text
adapter.sent == []
adapter.edits == []
projection["verdict"] == "accepted"
projection["side_effects"] == []
no snapshot/capture/platform/message identifiers in projection repr
```

**Verification command:**

```bash
scripts/run_tests.sh \
  tests/gateway/test_run_progress_topics.py::test_flowweaver_mock_durable_consumer_without_visible_side_effects \
  -q
python -m py_compile tests/gateway/test_run_progress_topics.py
```

### Task 6: Full focused gate, scans, and review

**Objective:** Prove the implementation remains confined, deterministic, and clean before PR.

**Commands:**

```bash
scripts/run_tests.sh \
  tests/gateway/test_flowweaver_mock_durable_consumer.py \
  tests/gateway/test_flowweaver_shadow_tap.py \
  tests/gateway/test_flowweaver_contract_adapter.py \
  tests/gateway/test_delivery_state.py \
  tests/gateway/test_run_progress_topics.py \
  tests/gateway/test_rich_weather_delivery.py \
  -q
python -m py_compile \
  gateway/flowweaver_mock_durable.py \
  tests/gateway/test_flowweaver_mock_durable_consumer.py \
  tests/gateway/test_run_progress_topics.py
git diff --check
```

Additional scans before commit/PR:

```text
forbidden path scan: no run_agent.py, model_tools.py, toolsets.py, cli.py, hermes_cli, gateway/run.py, gateway/platforms
forbidden runtime surface scan: no Temporal/Docker/service/Gateway restart/platform SDK/send/edit/render/persist/log calls in implementation files
sensitive added-line scan: no credential-shaped values or raw private identifiers
final candidate scan: no real credentials or platform-private IDs in modified files
```

Independent implementation reviews after code is written:

```text
spec / low-intrusion review: required
security / no-leak review: required
```

---

## Approval Gate

This plan records the design only. No implementation code should be written until the user explicitly approves Phase 4G execution after this plan/dev-log commit.

After design approval, implementation should proceed with strict RED → GREEN → regression → scan → review → commit → PR discipline.
