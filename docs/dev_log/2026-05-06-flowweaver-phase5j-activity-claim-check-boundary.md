# FlowWeaver Phase 5J — Activity / Claim-Check Boundary Dev Log

Timestamp: 2026-05-06 22:12:50 CST +0800

## Scope

User approved Phase 5J implementation after Phase 5I / PR #35 merge.

Phase 5J target:

```text
Add a prototype-only Temporal Activity / claim-check execution boundary to the FlowWeaver local runtime POC so a real local Worker can call safe stub Activities without leaking raw prompts, tool output, card JSON, platform IDs, or credentials into Workflow history or tool-visible snapshots.
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
real LLM/tool/shell/filesystem/network calls inside Activities
Gateway send/edit/render calls inside Activities
raw exception text in returned results, snapshots, logs, or docs
remote branch deletion
PR merge
```

## Baseline State

```text
canonical repo: /home/ubuntu/workspace/hermes/repo/sachima
canonical branch: feature/sachima-channel
canonical HEAD: 37752bc4e0841182677246285f3176c9a18573c2
origin/feature/sachima-channel: 37752bc4e0841182677246285f3176c9a18573c2
Phase 5J worktree: /home/ubuntu/workspace/hermes/worktrees/sachima/feat-flowweaver-phase5j-activity-claim-check-boundary
Phase 5J branch: feat/flowweaver-phase5j-activity-claim-check-boundary
```

Pre-existing canonical untracked items are not part of this phase:

```text
.hermes/
docs/plans/2026-04-24-sachima-channel.md
docs/superpowers/
```

## Context Inspected

```text
AGENTS.md
pyproject.toml
prototypes/flowweaver_phase5b_temporal_poc/pyproject.toml
prototypes/flowweaver_phase5b_temporal_poc/src/flowweaver_temporal_poc/__init__.py
prototypes/flowweaver_phase5b_temporal_poc/src/flowweaver_temporal_poc/payloads.py
prototypes/flowweaver_phase5b_temporal_poc/src/flowweaver_temporal_poc/workflows.py
prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/contracts.py
prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/runtime_client.py
prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/reconciliation_harness.py
tests/integration/test_flowweaver_phase5b_temporal_workflow.py
tests/integration/test_flowweaver_phase5h_local_temporal_worker_reconciliation.py
tests/integration/test_flowweaver_phase5i_start_signature_parity.py
tests/prototypes/test_flowweaver_phase5c_runtime_client_contract.py
tests/prototypes/test_flowweaver_phase5f_local_runtime_reconciliation.py
```

Current Temporal docs checked through Context7:

```text
npx ctx7@latest library temporalio "Python SDK workflow execute_activity activity definitions ActivityEnvironment testing"
  selected: /temporalio/sdk-python

npx ctx7@latest docs /temporalio/sdk-python "Python SDK execute_activity activity.defn ActivityEnvironment testing workflow history"
  evidence: ActivityEnvironment can unit-test Activities; WorkflowEnvironment.start_time_skipping() + Worker can run workflow/activity integration tests.

npx ctx7@latest docs /temporalio/sdk-python "workflow.execute_activity start_to_close_timeout activity.defn workflow unsafe imports passed through dataclass payloads"
  evidence: workflows can import activities through workflow.unsafe.imports_passed_through() and call workflow.execute_activity(..., start_to_close_timeout=...).
```

## Baseline Verification

Focused real local Temporal Worker regression before Phase 5J changes:

```text
TZ=UTC LANG=C.UTF-8 LC_ALL=C.UTF-8 PYTHONHASHSEED=0 \
  /home/ubuntu/.hermes/hermes-agent/venv/bin/python -m pytest -o addopts= -n 4 \
  tests/integration/test_flowweaver_phase5i_start_signature_parity.py \
  tests/integration/test_flowweaver_phase5h_local_temporal_worker_reconciliation.py \
  tests/integration/test_flowweaver_phase5c_runtime_client_temporal.py \
  tests/integration/test_flowweaver_phase5b_temporal_workflow.py \
  -q
# 24 passed in 1.39s
```

Affected prototype regression before Phase 5J changes:

```text
scripts/run_tests.sh \
  tests/prototypes/test_flowweaver_phase5i_start_signature_contract.py \
  tests/prototypes/test_flowweaver_phase5g_delivery_cardinality.py \
  tests/prototypes/test_flowweaver_phase5f_local_runtime_reconciliation.py \
  tests/prototypes/test_flowweaver_phase5e_local_publish_adapter.py \
  tests/prototypes/test_flowweaver_phase5e_variable_runtime_ids.py \
  tests/prototypes/test_flowweaver_phase5c_runtime_client_contract.py \
  tests/prototypes/test_flowweaver_phase5c_tool_adapter.py \
  tests/prototypes/test_flowweaver_phase5c_mcp_server_surface.py \
  tests/prototypes/test_flowweaver_phase5c_tool_surface.py \
  tests/prototypes/test_flowweaver_phase5b_temporal_payloads.py \
  -q
# 88 passed in 0.63s
```

## Plan

Plan saved at:

```text
docs/plans/2026-05-06-flowweaver-phase5j-activity-claim-check-boundary.md
```

Planned implementation files:

```text
prototypes/flowweaver_phase5b_temporal_poc/src/flowweaver_temporal_poc/activities.py
prototypes/flowweaver_phase5b_temporal_poc/src/flowweaver_temporal_poc/payloads.py
prototypes/flowweaver_phase5b_temporal_poc/src/flowweaver_temporal_poc/workflows.py
prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/contracts.py
prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/reconciliation_harness.py
tests/integration/test_flowweaver_phase5j_activity_claim_check_boundary.py
tests/prototypes/test_flowweaver_phase5j_activity_contract.py
```

Expected test maintenance files:

```text
tests/integration/test_flowweaver_phase5b_temporal_workflow.py
tests/integration/test_flowweaver_phase5h_local_temporal_worker_reconciliation.py
tests/integration/test_flowweaver_phase5i_start_signature_parity.py
tests/prototypes/test_flowweaver_phase5c_runtime_client_contract.py
tests/prototypes/test_flowweaver_phase5f_local_runtime_reconciliation.py
```

## Design status

Phase 5J plan has been drafted. Before implementation:

```text
1. Run doc gate for plan/dev log.
2. Run independent spec/TDD plan review.
3. Run independent security/low-intrusion/Temporal-boundary plan review.
4. Patch blockers if found.
5. Rerun doc gate after any plan/dev-log edits.
6. Proceed to strict RED tests only if reviews pass or remain within user-approved scope.
```

## Execution Log

### 2026-05-06 14:41:13 UTC — RED tests only

Added Phase 5J RED tests only; no prototype/production implementation files were modified.

Changed test files:

```text
tests/prototypes/test_flowweaver_phase5j_activity_contract.py
tests/integration/test_flowweaver_phase5j_activity_claim_check_boundary.py
```

Syntax check:

```text
python -m py_compile \
  tests/prototypes/test_flowweaver_phase5j_activity_contract.py \
  tests/integration/test_flowweaver_phase5j_activity_claim_check_boundary.py
# exit 0
```

Prototype RED command:

```text
scripts/run_tests.sh tests/prototypes/test_flowweaver_phase5j_activity_contract.py -q
# 6 failed in 0.40s
# Expected RED causes:
# - ImportError: ACTIVITY_BOUNDARY_TYPE / Phase 5J Activity dataclasses and validators are absent from flowweaver_temporal_poc.payloads.
# - KeyError: activity_boundary is stripped/missing from sanitized Phase 5C snapshots.
# - Failed: DID NOT RAISE ValueError for unknown nested activity_boundary fields because the sanitizer does not validate that field yet.
```

Integration/source RED command:

```text
TZ=UTC LANG=C.UTF-8 LC_ALL=C.UTF-8 PYTHONHASHSEED=0 \
  /home/ubuntu/.hermes/hermes-agent/venv/bin/python -m pytest -o addopts= -n 4 \
  tests/integration/test_flowweaver_phase5j_activity_claim_check_boundary.py -q
# 5 failed in 0.61s
# Expected RED causes:
# - ModuleNotFoundError: flowweaver_temporal_poc.activities does not exist for Worker Activity registration.
# - ImportError: AgentTurnActivityInput / validate_agent_turn_activity_input are absent.
# - AssertionError: workflow source has no workflow.execute_activity calls.
# - AssertionError: workflow source has no immediate pre-schedule Activity input validators.
```

Planned TDD evidence format:

```text
RED: record failing tests before implementation.
GREEN: record focused pass after the minimal implementation.
REFACTOR/GATES: record regression, static, security, and independent review evidence before commit.
```

### 2026-05-07 07:49 CST — GREEN and regression stabilization

Implemented the minimal prototype-only Activity / claim-check boundary:

```text
prototypes/flowweaver_phase5b_temporal_poc/src/flowweaver_temporal_poc/activities.py
prototypes/flowweaver_phase5b_temporal_poc/src/flowweaver_temporal_poc/payloads.py
prototypes/flowweaver_phase5b_temporal_poc/src/flowweaver_temporal_poc/workflows.py
prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/contracts.py
prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/reconciliation_harness.py
prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/runtime_client.py
```

Focused GREEN evidence:

```text
/home/ubuntu/.hermes/hermes-agent/venv/bin/python -m py_compile \
  prototypes/flowweaver_phase5b_temporal_poc/src/flowweaver_temporal_poc/payloads.py \
  prototypes/flowweaver_phase5b_temporal_poc/src/flowweaver_temporal_poc/workflows.py \
  prototypes/flowweaver_phase5b_temporal_poc/src/flowweaver_temporal_poc/activities.py \
  prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/contracts.py \
  prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/reconciliation_harness.py \
  tests/prototypes/test_flowweaver_phase5j_activity_contract.py \
  tests/integration/test_flowweaver_phase5j_activity_claim_check_boundary.py
/home/ubuntu/.hermes/hermes-agent/venv/bin/python -m pytest -o addopts= -q \
  tests/prototypes/test_flowweaver_phase5j_activity_contract.py \
  tests/integration/test_flowweaver_phase5j_activity_claim_check_boundary.py
# 12 passed in 0.73s
```

Regression stabilization notes:

```text
Initial Phase 5B/5C/5H/5I/5J regression after GREEN:
# 90 passed / 3 failed

Failures:
1. Phase 5H diff allowlist did not include Phase 5J files.
2. Phase 5I diff allowlist did not include Phase 5J files.
3. Phase 5H duplicate replay intermittently returned runtime_error under xdist/full regression.

Fixes:
- Added Phase 5J files to Phase 5H/5I/5J changed-file gates.
- Hardened FlowWeaverRuntimeClient duplicate-start handling for Temporal testing paths where WorkflowAlreadyStartedError can surface through a wrapper path; the catch now uses the narrow imported type plus a class-name fallback without reading/logging exception text.
- Added bounded safe-snapshot query retry for duplicate-start / delivery-ack replay paths to tolerate short-lived Temporal query readiness races without exposing raw exception strings.
```

Regression GREEN evidence:

```text
/home/ubuntu/.hermes/hermes-agent/venv/bin/python -m py_compile \
  prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/runtime_client.py \
  tests/integration/test_flowweaver_phase5h_local_temporal_worker_reconciliation.py
/home/ubuntu/.hermes/hermes-agent/venv/bin/python -m pytest -o addopts= -n 4 -q \
  tests/prototypes/test_flowweaver_phase5b_temporal_payloads.py \
  tests/prototypes/test_flowweaver_phase5c_runtime_client_contract.py \
  tests/prototypes/test_flowweaver_phase5f_local_runtime_reconciliation.py \
  tests/prototypes/test_flowweaver_phase5i_start_signature_contract.py \
  tests/prototypes/test_flowweaver_phase5j_activity_contract.py \
  tests/integration/test_flowweaver_phase5b_temporal_workflow.py \
  tests/integration/test_flowweaver_phase5c_runtime_client_temporal.py \
  tests/integration/test_flowweaver_phase5h_local_temporal_worker_reconciliation.py \
  tests/integration/test_flowweaver_phase5i_start_signature_parity.py \
  tests/integration/test_flowweaver_phase5j_activity_claim_check_boundary.py
# 93 passed in 1.76s
```

Static and security gates:

```text
git diff --check
# exit 0

/home/ubuntu/.hermes/hermes-agent/venv/bin/python -m py_compile <touched python files>
# exit 0

/home/ubuntu/.hermes/hermes-agent/venv/bin/python -m ruff check <touched python files>
# All checks passed!

refined source/security scan over git status paths
# refined_security_scan=pass
```

Remaining before commit:

```text
1. Rerun diff/static/security gates after this dev-log/plan edit.
2. Run independent implementation/security review.
3. Fix any reviewer blockers with tests first.
4. Commit, push, and open PR if clean.
```

### 2026-05-07 07:50 CST — Independent implementation/security review

Codex CLI review command:

```text
GIT_PAGER=cat PAGER=cat codex -C /home/ubuntu/workspace/hermes/worktrees/sachima/feat-flowweaver-phase5j-activity-claim-check-boundary \
  -s read-only -a never exec --output-last-message /home/ubuntu/workspace/hermes/tmp/phase5j_codex_review.md - \
  < /home/ubuntu/workspace/hermes/tmp/phase5j_codex_review_prompt.md
# exit 0
```

Review verdict:

```text
Verdict: PASS

Checked invariants:
- No raw-material leak found in Activity input/result/snapshot/history surfaces.
- Every workflow.execute_activity call is immediately preceded by validation of the exact scheduled object.
- Activities are stub-only with no Gateway/tools/network/filesystem/logging/model/send/edit/render imports or calls.
- No production-surface or dependency scope creep found.
- runtime_client duplicate-start/replay hardening stays fail-closed and does not return raw exception text.
```

Final post-review gates at 2026-05-07 08:02 CST:

```text
git diff --check
# exit 0

/home/ubuntu/.hermes/hermes-agent/venv/bin/python -m py_compile <touched python files>
# exit 0

/home/ubuntu/.hermes/hermes-agent/venv/bin/python -m ruff check <touched python files>
# All checks passed!

/home/ubuntu/.hermes/hermes-agent/venv/bin/python -m pytest -o addopts= -n 4 -q \
  tests/prototypes/test_flowweaver_phase5b_temporal_payloads.py \
  tests/prototypes/test_flowweaver_phase5c_runtime_client_contract.py \
  tests/prototypes/test_flowweaver_phase5f_local_runtime_reconciliation.py \
  tests/prototypes/test_flowweaver_phase5i_start_signature_contract.py \
  tests/prototypes/test_flowweaver_phase5j_activity_contract.py \
  tests/integration/test_flowweaver_phase5b_temporal_workflow.py \
  tests/integration/test_flowweaver_phase5c_runtime_client_temporal.py \
  tests/integration/test_flowweaver_phase5h_local_temporal_worker_reconciliation.py \
  tests/integration/test_flowweaver_phase5i_start_signature_parity.py \
  tests/integration/test_flowweaver_phase5j_activity_claim_check_boundary.py
# 93 passed in 1.75s

refined source/security scan over git status paths
# refined_security_scan=pass
```

Ready for commit, push, and PR creation.
