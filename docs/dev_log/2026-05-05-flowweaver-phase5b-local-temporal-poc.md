# FlowWeaver Phase 5B — Local Temporal POC Dev Log

Timestamp: 2026-05-05 13:49:11 CST +0800

## Scope

Start Phase 5B after Phase 5A was merged. Phase 5B is a local-only Temporal proof of concept under `prototypes/`, using the Phase 5A safe runtime ingress envelope as the only durable start boundary.

This phase must keep **no Gateway wiring**, **no Gateway restart**, **no Docker**, **no service auto-start**, no platform adapter mutation, no production persistence, and no visible IM behavior change.

## User instruction

User requested in Feishu:

```text
执行下一个阶段
```

Interpreted as moving from completed Phase 5A to Phase 5B:

```text
Phase 5B: Local Temporal POC
```

Design approval remains a hard gate before code implementation.

## Branch and worktree

```text
branch: feat/flowweaver-phase5b-local-temporal-poc
worktree: /home/ubuntu/workspace/hermes/worktrees/sachima/feat-flowweaver-phase5b-local-temporal-poc
base: origin/feature/sachima-channel @ f16391681c19f10c99bf5d8e1fd5dc3484fa1409
```

Canonical repo before branching:

```text
path: /home/ubuntu/workspace/hermes/repo/sachima
branch: feature/sachima-channel
head: f16391681c19f10c99bf5d8e1fd5dc3484fa1409
origin_head: f16391681c19f10c99bf5d8e1fd5dc3484fa1409
canonical/origin ahead-behind: 0 / 0
open PRs on base: []
```

Canonical had existing local untracked items outside this worktree:

```text
.hermes/
docs/plans/2026-04-24-sachima-channel.md
docs/superpowers/
```

These were not copied into the Phase 5B worktree and are not part of this phase.

## Gateway status during discovery

```text
hermes-gateway.service: active/running
MainPID: 3480137
ExecMainStartTimestamp: Tue 2026-05-05 13:35:33 CST
WorkingDirectory: /home/ubuntu/workspace/hermes/repo/sachima
```

No Gateway restart is planned for Phase 5B.

## Temporal tooling discovery

Observed before implementation:

```text
Temporal CLI: temporal version 1.7.0 (Server 1.31.0, UI 2.49.1)
Temporal Python SDK in current gateway venv: missing before Phase 5B
PyPI temporalio latest observed: 1.27.0
Context7 docs checked: /temporalio/sdk-python, /temporalio/cli
```

Relevant docs notes from Context7:

```text
- Workflows use @workflow.defn and @workflow.run.
- Queries use @workflow.query.
- Signals use @workflow.signal, but Phase 5B will not use payload-carrying Signals because Signal arguments enter history before handler-side validation.
- Updates use @workflow.update; validators can reject invalid updates before history is accepted.
- Tests can use WorkflowEnvironment with Worker for local workflow execution.
- temporal server start-dev starts a local development server; Phase 5B code must not auto-start it.
```

## Baseline verification

Command:

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
  gateway/flowweaver_shadow.py \
  gateway/flowweaver_mock_durable.py \
  gateway/flowweaver_shadow_dry_run.py
```

Observed:

```text
152 passed in 21.85s
py_compile: passed
```

## Context inspected

```text
AGENTS.md
docs/plans/2026-05-05-flowweaver-phase5-architecture-gate.md
docs/plans/2026-05-05-flowweaver-phase5a-durable-runtime-ingress-contract.md
docs/dev_log/2026-05-05-flowweaver-phase5a-durable-runtime-ingress-contract.md
gateway/flowweaver_runtime_contract.py
tests/gateway/test_flowweaver_runtime_contract.py
prototypes/flowweaver_phase3/src/flowweaver_mock/models.py
prototypes/flowweaver_phase3/src/flowweaver_mock/orchestrator.py
pyproject.toml
.github/workflows/tests.yml
```

## Planned files

Allowed files after implementation approval:

```text
docs/plans/2026-05-05-flowweaver-phase5b-local-temporal-poc.md
docs/dev_log/2026-05-05-flowweaver-phase5b-local-temporal-poc.md
pyproject.toml
uv.lock
prototypes/flowweaver_phase5b_temporal_poc/pyproject.toml
prototypes/flowweaver_phase5b_temporal_poc/README.md
prototypes/flowweaver_phase5b_temporal_poc/src/flowweaver_temporal_poc/__init__.py
prototypes/flowweaver_phase5b_temporal_poc/src/flowweaver_temporal_poc/payloads.py
prototypes/flowweaver_phase5b_temporal_poc/src/flowweaver_temporal_poc/workflows.py
prototypes/flowweaver_phase5b_temporal_poc/src/flowweaver_temporal_poc/client.py
tests/prototypes/test_flowweaver_phase5b_temporal_payloads.py
tests/integration/test_flowweaver_phase5b_temporal_workflow.py
```

Explicitly not planned:

```text
gateway/run.py
gateway/platforms/*
run_agent.py
model_tools.py
toolsets.py
cli.py
hermes_cli/*
Docker files
systemd service files
Gateway restart
production persistence
```

## Design status

Plan drafted:

```text
docs/plans/2026-05-05-flowweaver-phase5b-local-temporal-poc.md
```

Planned prototype:

```text
prototypes/flowweaver_phase5b_temporal_poc/
```

Planned public surfaces:

```text
flowweaver_temporal_poc.payloads
flowweaver_temporal_poc.workflows.FlowWeaverTransactionWorkflow
flowweaver_temporal_poc.client  # manual/local helper only
```

## Verification before implementation

Initial doc-only verification:

```text
git check-ignore planned files: no ignored-path blocker observed
git diff --check: passed
doc marker scan: passed
secret/private-id shaped literal scan: passed
changed files at design gate:
  docs/dev_log/2026-05-05-flowweaver-phase5b-local-temporal-poc.md
  docs/plans/2026-05-05-flowweaver-phase5b-local-temporal-poc.md
```

First doc gate attempt failed because the dev log did not contain the exact boundary marker strings used by the verifier. This was a verifier/document marker issue, not a product implementation issue. The dev log wording was patched to include exact `no Gateway wiring`, `no Gateway restart`, `no Docker`, and `no service auto-start` markers; the full doc gate was rerun and passed.

Final doc gate after reviewer blocker patches:

```text
git diff --check: passed
doc marker scan: passed
secret/private-id shaped literal scan: passed
changed files:
  docs/dev_log/2026-05-05-flowweaver-phase5b-local-temporal-poc.md
  docs/plans/2026-05-05-flowweaver-phase5b-local-temporal-poc.md
```

## TDD status

Implementation not started. Next step after plan approval:

```text
RED: tests/prototypes/test_flowweaver_phase5b_temporal_payloads.py
```

Expected initial RED:

```text
flowweaver-temporal extra missing
ModuleNotFoundError: No module named 'flowweaver_temporal_poc'
```

## Independent review

Initial plan review result:

```text
Spec / low-intrusion reviewer: PASS, no blockers.
Security / no-leak / Temporal-determinism reviewer: BLOCKER.
```

Security reviewer blockers and plan fixes:

```text
1. Payload-carrying Signal was unsafe for no-leak history posture.
   Fix: Phase 5B now uses validated Updates only for payload-carrying external events; no payload-carrying Signals.
2. Update validation wording was optional/incomplete.
   Fix: every external Update now requires a typed safe payload builder plus Workflow Update validator.
3. ACK / human payload shapes were not strict enough.
   Fix: plan now requires closed enums, synthetic ID patterns, claim-check refs, and explicit platform/private/credential-shaped rejection tests.
4. Temporal determinism gates were incomplete.
   Fix: plan now requires static/AST tests for common nondeterminism and forbids Activity scheduling in Phase 5B.
5. Missing Temporal history no-leak verification.
   Fix: integration gate now requires history/query/result representation no-leak checks after safe start and safe Updates.
6. Client helper address default conflicted with explicit-local safety.
   Fix: `connect_local_temporal(address: str)` now requires an explicit address.
```

Final blocker-only re-review found one remaining blocker:

```text
The plan architecture summary still said “Updates or Signals”.
```

Fix applied:

```text
Architecture summary now says approval/cancellation/resume/delivery-ACK are accepted as Updates from safe FlowWeaver envelopes and explicitly says Phase 5B does not use payload-carrying Signals.
```

Final blocker-only re-review after this wording fix:

```text
Security / no-leak / Temporal-determinism reviewer: PASS, no remaining blockers.
```

Reviewer confirmed the plan has no remaining active `Updates or Signals` / `Update or Signal` wording; the old phrase appears only in this dev log as historical blocker context plus fix record.

## Implementation after approval

Timestamp: 2026-05-05 18:01:16 CST +0800

User approved Phase 5B implementation in Feishu:

```text
批准 Phase 5B 实现
```

Loaded and applied relevant workflow skills:

```text
test-driven-development: RED/GREEN kept for dependency/package, payload boundary, workflow, and client helper.
temporal-durable-orchestration: Updates with validators only; Workflow owns deterministic state; no Activities in Phase 5B.
context7/find-docs: verified Temporal Python SDK update validators, WorkflowEnvironment, and history APIs; verified uv package-specific exclude-newer syntax.
verification-before-completion/requesting-code-review: gates and independent review remain required before PR.
```

State verified before implementation:

```text
Gateway process observed: /home/ubuntu/.hermes/hermes-agent/venv/bin/python -m hermes_cli.main gateway run --replace
Gateway PID observed: 3480137
canonical branch: feature/sachima-channel...origin/feature/sachima-channel
Phase 5B branch: feat/flowweaver-phase5b-local-temporal-poc...origin/feature/sachima-channel
Phase 5B worktree changed files before implementation: plan + dev log only
```

TDD evidence:

```text
RED Task 1:
  scripts/run_tests.sh tests/prototypes/test_flowweaver_phase5b_temporal_payloads.py -q
  observed: 2 failed
  expected failures: flowweaver-temporal extra missing; flowweaver_temporal_poc package missing

GREEN Task 2:
  added optional extra flowweaver-temporal; added prototype package shell; updated uv.lock
  scripts/run_tests.sh tests/prototypes/test_flowweaver_phase5b_temporal_payloads.py -q
  observed: 2 passed

RED Task 3:
  added payload boundary tests
  scripts/run_tests.sh tests/prototypes/test_flowweaver_phase5b_temporal_payloads.py -q
  observed: 7 failed, 2 passed
  expected failure: flowweaver_temporal_poc.payloads missing

GREEN Task 4:
  added safe payload projection and validators
  scripts/run_tests.sh tests/prototypes/test_flowweaver_phase5b_temporal_payloads.py -q
  observed: 9 passed

RED Task 5:
  added local Temporal workflow integration/static tests
  python -m pytest tests/integration/test_flowweaver_phase5b_temporal_workflow.py -q -m integration -o 'addopts='
  observed: collection error because flowweaver_temporal_poc.workflows missing

GREEN Task 6:
  added deterministic Temporal Workflow with Query + validated Updates only
  first integration attempt exposed Temporal Python SDK converter constraints: dataclass fields/return annotations using object caused decode failures
  fix: changed RuntimeStartPayload.claim_check_policy to dict[str, Any] and workflow returns to dict[str, Any]
  python -m pytest tests/integration/test_flowweaver_phase5b_temporal_workflow.py -q -m integration -o 'addopts='
  observed: 8 passed

RED Task 7:
  added client helper tests
  scripts/run_tests.sh tests/prototypes/test_flowweaver_phase5b_temporal_payloads.py -q
  observed: 3 failed, 9 passed
  expected failure: flowweaver_temporal_poc.client missing

GREEN Task 7:
  added manual/local client helper with explicit address/workflow ID validation and no service start
  scripts/run_tests.sh tests/prototypes/test_flowweaver_phase5b_temporal_payloads.py -q
  observed: 12 passed
```

Resolver note:

```text
Initial /home/linuxbrew/.linuxbrew/bin/uv lock failed because repo-level exclude-newer = "7 days" filtered out temporalio 1.27.0.
Fix kept the supply-chain exception narrow: [tool.uv].exclude-newer-package = { temporalio = "2026-05-01T00:00:00Z" }
Final uv lock observed:
  Added nexus-rpc v1.4.0
  Added temporalio v1.27.0
  Added types-protobuf v6.32.1.20260221
```

Current implementation boundary:

```text
no Gateway wiring
no gateway/run.py changes
no gateway/platforms/* changes
no run_agent.py/model_tools.py/toolsets.py/cli.py/hermes_cli changes
no Docker
no Gateway restart
no production service auto-start
no platform send/edit/render calls
no production persistence
workflow has no Activities and no payload-carrying Signals
```

## Pre-PR verification

Timestamp: 2026-05-05 18:31:24 CST +0800

Focused verification after implementation and reviewer fixes:

```text
scripts/run_tests.sh \
  tests/prototypes/test_flowweaver_phase5b_temporal_payloads.py \
  tests/gateway/test_flowweaver_runtime_contract.py \
  tests/gateway/test_flowweaver_shadow_dry_run.py \
  tests/gateway/test_flowweaver_mock_durable_consumer.py \
  tests/gateway/test_flowweaver_shadow_tap.py \
  tests/gateway/test_run_progress_topics.py \
  -q
observed: 138 passed in 18.10s

python -m pytest tests/integration/test_flowweaver_phase5b_temporal_workflow.py -q -m integration -o 'addopts='
observed: 8 passed in 0.86s

python -m py_compile changed Phase 5B Python files
observed: passed

git diff --check
observed: passed

custom allowed-file / forbidden-path / temporalio-import / side-effect / workflow / secret scan
observed: passed
```

Independent review status:

```text
Spec / low-intrusion reviewer: PASS, no blockers.
Security / no-leak / Temporal-determinism reviewer: initially BLOCKED, then PASS after two fix rounds.
```

Security reviewer blocker round 1:

```text
1. `_synthetic_id` accepted embedded platform/private IDs after safe prefixes, allowing unsafe Update payloads into Temporal history.
2. `claim_check_policy['forbidden_material']` accepted arbitrary attacker-controlled or credential-shaped strings, allowing unsafe start payload material into Temporal history.
```

Fix round 1:

```text
RED tests added:
  test_start_payload_rejects_attacker_controlled_claim_check_policy_values
  test_update_builders_reject_embedded_platform_ids_after_safe_prefixes
Implementation:
  added exact `_EXPECTED_FORBIDDEN_MATERIAL` closed list
  `_claim_check_policy` rejects deviations from the closed list
  `_synthetic_id` rejects embedded platform/private markers after approved prefixes
  history test now scans protobuf event bytes via `SerializeToString()` in addition to JSON text
Verification:
  scripts/run_tests.sh tests/prototypes/test_flowweaver_phase5b_temporal_payloads.py -q => 14 passed
  python -m pytest tests/integration/test_flowweaver_phase5b_temporal_workflow.py -q -m integration -o 'addopts=' => 8 passed
```

Security reviewer blocker round 2:

```text
1. Marker filter still allowed one-character-prefixed bypasses such as runtime_event_xchat_123.
2. Client workflow ID validation did not reuse the same no-leak marker filtering.
```

Fix round 2:

```text
RED tests expanded for xchat/xmessage/xplatform/xou/claim_ref_xchat bypasses and unsafe runtime_tx workflow IDs.
Implementation:
  `_synthetic_id` now rejects any private/platform marker in the post-prefix body
  added `validate_runtime_workflow_id()`
  client `_validate_workflow_id()` now reuses `validate_runtime_workflow_id()`
Verification:
  scripts/run_tests.sh tests/prototypes/test_flowweaver_phase5b_temporal_payloads.py -q => 14 passed
  python -m pytest tests/integration/test_flowweaver_phase5b_temporal_workflow.py -q -m integration -o 'addopts=' => 8 passed
  second blocker-only reviewer: PASS, no blockers, no warnings
```
