# FlowWeaver Phase 4 Gateway Contract Seam Implementation Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task after explicit user approval.

**Goal:** Add the first production-adjacent FlowWeaver seam: a low-intrusion, testable translator from existing Gateway progress/delivery state into a sanitized `flowweaver.v0` snapshot, without enabling orchestration or changing live IM behavior.

**Architecture:** Phase 4A deliberately does **not** introduce Temporal, DAG scheduling, agent-loop rewriting, or Gateway runtime wiring. It adds a pure adapter module plus tests that prove current Sachima/Hermes progress state can be represented in the Phase 3 `flowweaver.v0` contract. Runtime persistence/rendering is deferred to later phases behind separate approval.

**Tech Stack:** Python, pytest, existing `gateway.progress.*`, existing `gateway.delivery_state`, Phase 3 `prototypes/flowweaver_phase3/contracts/flowweaver.v0.schema.json` semantics.

---

## Current Context / Evidence

Timestamp: 2026-05-04 12:17:41 CST +0800

Current repo state verified before writing this plan:

```text
repo: /home/ubuntu/workspace/hermes/repo/sachima
branch: feature/sachima-channel
HEAD: 9a34910f2
remote sync: 0 ahead / 0 behind
open PRs: none
focused verification:
  scripts/run_tests.sh tests/flowweaver_phase3 -q -> 23 passed, 3 subtests passed
  pytest tests/gateway/test_delivery_state.py tests/gateway/test_run_rich_weather.py tests/gateway/progress/test_task_titles.py -q -> 52 passed
```

Relevant current surfaces:

- Phase 3 inert contract/harness:
  - `prototypes/flowweaver_phase3/contracts/flowweaver.v0.schema.json`
  - `prototypes/flowweaver_phase3/src/flowweaver_mock/*`
  - `tests/flowweaver_phase3/*`
- Gateway progress state:
  - `gateway/progress/events.py`
  - `gateway/progress/tracker.py`
  - `gateway/progress/store.py`
  - `gateway/progress/renderers.py`
- Gateway delivery state:
  - `gateway/delivery_state.py`
  - `tests/gateway/test_delivery_state.py`
- Current rich-card/final-text invariant:
  - rich card sent != final text sent
  - `delivery_state.final_text.sent=True` is the only explicit final-text suppression state.

Repo hygiene note:

```text
untracked local-only planning artifacts currently exist:
.hermes/plans/*
docs/plans/2026-04-24-sachima-channel.md
docs/superpowers/specs/2026-04-24-sachima-channel-design.md
```

Do not mix cleanup of these historical files into the FlowWeaver Phase 4 code PR unless 狗哥 explicitly approves a separate hygiene PR.

---

## Non-Goals / Hard Boundaries

Phase 4A must not do any of this:

```text
no Temporal
no Docker
no background daemons
no service startup
no Gateway restart
no live IM behavior change
no model/tool-loop rewrite
no changes to run_agent.py
no changes to model_tools.py
no changes to toolsets.py
no default skill activation
no Feishu SDK calls from FlowWeaver adapter code
```

Forbidden or high-risk surfaces for Phase 4A:

```text
run_agent.py
model_tools.py
toolsets.py
cli.py
hermes_cli/main.py
gateway/platforms/*
skills/*
optional-skills/*
root pyproject.toml
```

Allowed code/doc surfaces for the first PR:

```text
gateway/flowweaver_contract.py
tests/gateway/test_flowweaver_contract_adapter.py
docs/plans/2026-05-04-flowweaver-phase4-gateway-contract-seam.md
docs/dev_log/2026-05-04-flowweaver-phase4-gateway-contract-seam.md
```

Optional allowed surface only if a test proves it is cleaner than a standalone file:

```text
gateway/flowweaver_contract/__init__.py
gateway/flowweaver_contract/adapter.py
```

Prefer the single-file module first. YAGNI wins.

---

## Branch / Worktree Plan

Create a fresh worktree from the integration branch:

```bash
cd /home/ubuntu/workspace/hermes/repo/sachima
git fetch origin feature/sachima-channel
BRANCH=feat/flowweaver-phase4-gateway-contract-seam
git worktree add /home/ubuntu/workspace/hermes/worktrees/sachima/feat-flowweaver-phase4-gateway-contract-seam -b "$BRANCH" origin/feature/sachima-channel
cd /home/ubuntu/workspace/hermes/worktrees/sachima/feat-flowweaver-phase4-gateway-contract-seam
```

First commit on the branch should persist this approved plan into the repo:

```text
docs/plans/2026-05-04-flowweaver-phase4-gateway-contract-seam.md
```

Commit body should include:

```text
Plan: docs/plans/2026-05-04-flowweaver-phase4-gateway-contract-seam.md
```

---

## Design: Phase 4A Adapter Contract

Add a pure function boundary:

```python
def build_flowweaver_v0_snapshot(
    progress_snapshot: TransactionSnapshot,
    *,
    source: dict[str, Any] | None = None,
    delivery_state: dict[str, Any] | None = None,
    final_text: str | None = None,
) -> dict[str, Any]:
    """Return a sanitized flowweaver.handle.v0 snapshot for existing Gateway task state."""
```

Initial mapping rules:

1. One existing `TransactionSnapshot` maps to one FlowWeaver transaction.
2. Phase 4A uses a single synthetic intent:
   - `intent_id`: `task`
   - `order_index`: `0`
   - `title`: sanitized `progress_snapshot.title`
3. Existing progress operations map to FlowWeaver operations:
   - `op_<safe_id>` ids
   - `kind` derived from event/tool name, sanitized and slugified
   - no raw args/output/commands
   - `inputs_summary` may be omitted or bounded/sanitized
4. Status vocabulary translation:
   - `running` -> `running`
   - `pending` -> `pending`
   - `completed` -> `succeeded`
   - `failed` -> `failed`
   - `blocked` -> `blocked`
   - `cancelled` -> `cancelled`
5. Final text coverage:
   - If `delivery_state.final_text.sent is True`, create a final-text delivery ACK targeting `final_text` and set coverage mode `answered`.
   - If final text exists but is not sent, coverage remains `blocked_waiting_for_user` or pending-equivalent by contract.
6. Rich-card delivery state:
   - If `delivery_state.rich_cards_sent` contains records with `type` and `message_id`, create compact rich-card artifacts and delivery ACKs.
   - Do **not** infer rich-card delivery from prose, raw card JSON, or unsent artifact data.
7. `adapter` stays `gateway_adapter` or another explicit non-mock adapter value only if the contract is updated. If v0 schema still requires `adapter: mock`, Phase 4A should either:
   - keep generated snapshots as internal test fixtures with `adapter: mock_adapter`, and update the schema in a versioned way only in a separate PR; or
   - preserve `adapter: mock` for compatibility and document that Phase 4A is a contract-shaped exporter, not the real orchestrator.

Preferred choice for first PR: **preserve v0 compatibility** and do not mutate the schema unless tests show this is untenable.

---

## Task 0: Persist Approved Plan

**Objective:** Create a repo-visible plan artifact before code, per AI FLOW.

**Files:**

- Create: `docs/plans/2026-05-04-flowweaver-phase4-gateway-contract-seam.md`

**Step 1: Copy this plan into repo docs**

Use file tools to create the docs plan in the Phase 4 worktree.

**Step 2: Verify docs path is tracked**

Run:

```bash
git check-ignore -v docs/plans/2026-05-04-flowweaver-phase4-gateway-contract-seam.md || true
```

Expected: no ignore match.

**Step 3: Commit plan only**

```bash
git add docs/plans/2026-05-04-flowweaver-phase4-gateway-contract-seam.md
git commit -m "docs: plan FlowWeaver phase 4 gateway contract seam" -m "Plan: docs/plans/2026-05-04-flowweaver-phase4-gateway-contract-seam.md"
```

---

## Task 1: RED — Contract Adapter Test Skeleton

**Objective:** Add failing tests that describe the Gateway-to-FlowWeaver v0 adapter contract before implementation exists.

**Files:**

- Create: `tests/gateway/test_flowweaver_contract_adapter.py`
- No production file yet.

**Step 1: Write failing tests**

Test cases to include:

```python
def test_builds_single_intent_snapshot_from_progress_tracker_state(): ...
def test_translates_gateway_status_vocabulary_to_flowweaver_v0_statuses(): ...
def test_maps_progress_operations_without_raw_args_or_outputs(): ...
def test_final_text_delivery_state_counts_as_answered_coverage(): ...
def test_rich_card_delivery_state_creates_artifact_and_delivery_without_suppressing_final_text(): ...
def test_secret_shaped_values_are_redacted_in_snapshot_repr(): ...
```

**Step 2: Run RED**

```bash
/home/ubuntu/.hermes/hermes-agent/venv/bin/python -m pytest tests/gateway/test_flowweaver_contract_adapter.py -q
```

Expected: fail because `gateway.flowweaver_contract` does not exist.

---

## Task 2: GREEN — Minimal Pure Adapter Module

**Objective:** Implement the smallest pure module that satisfies Task 1 tests without runtime wiring.

**Files:**

- Create: `gateway/flowweaver_contract.py`
- Test: `tests/gateway/test_flowweaver_contract_adapter.py`

**Implementation shape:**

```python
from __future__ import annotations

from typing import Any

from gateway.progress.events import ProgressOperation, TransactionSnapshot
from gateway.progress.redaction import sanitize_for_progress, sanitize_value_for_progress

FLOWWEAVER_CONTRACT_VERSION = "flowweaver.v0"
FLOWWEAVER_HANDLE_TYPE = "flowweaver.handle.v0"


def build_flowweaver_v0_snapshot(
    progress_snapshot: TransactionSnapshot,
    *,
    source: dict[str, Any] | None = None,
    delivery_state: dict[str, Any] | None = None,
    final_text: str | None = None,
) -> dict[str, Any]:
    ...
```

Keep helper functions local and boring:

```text
_safe_id
_slugify
_status_to_flowweaver
_operation_to_record
_delivery_state_to_artifacts_and_deliveries
_intent_coverage
_safe_iso_time
```

No imports from `prototypes/flowweaver_phase3` in production code. The prototype remains inert reference material.

**Step 2: Run GREEN**

```bash
/home/ubuntu/.hermes/hermes-agent/venv/bin/python -m pytest tests/gateway/test_flowweaver_contract_adapter.py -q
```

Expected: all new tests pass.

---

## Task 3: Add Contract-Invariant Reuse Tests

**Objective:** Ensure the production-adjacent adapter obeys the same critical safety invariants as Phase 3 snapshots.

**Files:**

- Modify: `tests/gateway/test_flowweaver_contract_adapter.py`

**Add checks for:**

- envelope keys include `type`, `transaction_id`, `correlation_id`, `snapshot_id`, `contract_version`, `transaction`, `snapshot`
- all statuses are in FlowWeaver vocabulary
- no forbidden keys:
  - `authorization`
  - `api_key`
  - `secret`
  - `token`
  - `raw_args`
  - `raw_command`
  - `raw_output`
  - `stdout`
  - `stderr`
  - `feishu_card_json`
- no forbidden value patterns:
  - authorization-header patterns
  - OpenAI-style `sk-` key patterns
  - fake token/secret strings used in test fixtures
- rich-card delivery ACK does not mark final text answered unless final text delivery ACK exists

**Run:**

```bash
/home/ubuntu/.hermes/hermes-agent/venv/bin/python -m pytest tests/gateway/test_flowweaver_contract_adapter.py tests/gateway/test_delivery_state.py -q
```

Expected: pass.

---

## Task 4: Integration-Seam Regression With Existing Progress Tracker

**Objective:** Prove the adapter can consume real current Gateway progress objects without changing Gateway runtime behavior.

**Files:**

- Modify: `tests/gateway/test_flowweaver_contract_adapter.py`

**Test setup:**

Use existing `ProgressTracker`:

```python
tracker = ProgressTracker(transaction_id="session-123", title="说明当前模型与思考强度配置")
tracker.record_tool_started("terminal", preview="python script.py --token fake-token")
tracker.record_tool_completed("terminal", duration=0.42, preview="done token=fake-token")
snapshot = tracker.snapshot()
```

Then pass through `build_flowweaver_v0_snapshot(...)`.

Assertions:

- transaction title is preserved as sanitized intent summary
- operation exists
- fake token is absent from `repr(flowweaver_snapshot)`
- adapter output contains no raw command line
- no Gateway send/edit/platform adapter is called

**Run:**

```bash
/home/ubuntu/.hermes/hermes-agent/venv/bin/python -m pytest \
  tests/gateway/test_flowweaver_contract_adapter.py \
  tests/gateway/test_progress_tracker.py \
  tests/gateway/test_progress_store.py \
  -q
```

Expected: pass.

---

## Task 5: Documentation / Dev Log

**Objective:** Record exactly what Phase 4A did, why it is low-intrusion, and what remains deliberately deferred.

**Files:**

- Create: `docs/dev_log/2026-05-04-flowweaver-phase4-gateway-contract-seam.md`

Dev log must include:

- timestamp
- branch/worktree/base commit
- scope
- changed files
- low-intrusion boundary
- TDD RED/GREEN evidence
- verification commands/results
- security notes
- missed-test reflection
- explicit statement: no Gateway restart, no Temporal, no runtime wiring

---

## Task 6: Verification Gate

**Objective:** Verify the branch before PR.

Run from the Phase 4 worktree:

```bash
scripts/run_tests.sh \
  tests/gateway/test_flowweaver_contract_adapter.py \
  tests/gateway/test_delivery_state.py \
  tests/gateway/test_run_progress_topics.py \
  tests/gateway/test_rich_weather_delivery.py \
  -q

/home/ubuntu/.hermes/hermes-agent/venv/bin/python -m py_compile \
  gateway/flowweaver_contract.py \
  tests/gateway/test_flowweaver_contract_adapter.py

git diff --check
```

Add deterministic hygiene scans:

```bash
python - <<'PY'
from pathlib import Path
forbidden = [
    'run_agent.py', 'model_tools.py', 'toolsets.py', 'cli.py', 'hermes_cli/main.py',
]
changed = [line.strip() for line in __import__('subprocess').check_output(['git','diff','--name-only','origin/feature/sachima-channel...HEAD'], text=True).splitlines()]
violations = [p for p in changed if p in forbidden or p.startswith('gateway/platforms/') or p.startswith('skills/') or p.startswith('optional-skills/')]
print('changed_files=', changed)
print('forbidden_violations=', violations)
raise SystemExit(1 if violations else 0)
PY
```

Secret scan over changed files:

```bash
python - <<'PY'
import re, subprocess, sys
patterns = [
    re.compile('Bearer' + r'\s+[A-Za-z0-9._-]+', re.I),
    re.compile('sk-' + r'[A-Za-z0-9]{12,}'),
    re.compile(r'AKIA[0-9A-Z]{16}'),
    re.compile(r'-----BEGIN [A-Z ]+PRIVATE KEY-----'),
]
text = subprocess.check_output(['git', 'diff', '--cached'], text=True, errors='replace')
findings = [p.pattern for p in patterns if p.search(text)]
print('secret_findings=', findings)
sys.exit(1 if findings else 0)
PY
```

Expected: all pass.

---

## Task 7: Independent Reviews Before PR

**Objective:** Catch design/security blockers before PR.

Run two focused reviews, preferably with `delegate_task`:

1. Spec/contract/low-intrusion review:
   - Does this preserve FlowWeaver v0 semantics?
   - Does it avoid runtime behavior changes?
   - Does it mutate forbidden surfaces?
   - Does final coverage remain explicit?

2. Security/display review:
   - Does any snapshot contain raw args/output/card JSON/secrets?
   - Are delivery ACKs only derived from explicit delivery state?
   - Could a malicious progress preview inject Feishu/card content?

Patch real blockers immediately. Do not broaden scope to orchestration.

---

## Task 8: Commit, Push, PR

**Objective:** Open a reviewable PR against `feature/sachima-channel`.

Use conventional commits. Suggested commits:

```text
docs: plan FlowWeaver phase 4 gateway contract seam
test: define FlowWeaver gateway contract adapter behavior
feat: add FlowWeaver gateway contract adapter
docs: record FlowWeaver phase 4 gateway contract seam
```

Push:

```bash
git push -u origin feat/flowweaver-phase4-gateway-contract-seam
```

Open PR:

```bash
/home/linuxbrew/.linuxbrew/bin/gh pr create \
  -R jovijovi/sachima \
  --base feature/sachima-channel \
  --head feat/flowweaver-phase4-gateway-contract-seam \
  --title "feat: add FlowWeaver gateway contract seam" \
  --body-file /tmp/flowweaver-phase4-pr.md
```

PR body must include:

- summary
- plan path
- dev log path
- tests/verification
- low-intrusion proof
- runtime impact: none
- no gateway restart performed

---

## Risks / Tradeoffs

1. **Synthetic single intent is intentionally limited.**
   - This avoids inventing production multi-intent orchestration too early.
   - Phase 4B should add real intent planning only after this mapping seam is stable.

2. **Schema adapter value ambiguity.**
   - Current v0 schema says `adapter: mock`.
   - Do not casually mutate the schema in Phase 4A; that risks breaking golden snapshots.
   - If production adapter naming is required, create `flowweaver.v1` or a tiny schema-compatible extension in a separate PR.

3. **Delivery ACK ownership must stay Gateway-owned.**
   - The adapter may translate existing confirmed state.
   - It must not claim new sends or call platform APIs.

4. **Progress snapshots are user-facing surfaces.**
   - Sanitize at adapter input and output.
   - Tests must prove no raw command/arg/output/card JSON leakage.

5. **Runtime wiring is deferred.**
   - This is a feature, not a bug. Hard-wiring now would be reckless.

---

## Proposed Roadmap After Phase 4A

Only after Phase 4A merges and is verified:

### Phase 4B — Optional Persistence

Add off-by-default config to persist FlowWeaver contract snapshots alongside progress JSONL:

```yaml
display:
  task_tracker:
    flowweaver_snapshots: false
```

No UI behavior change by default.

### Phase 4C — Intent Planner Seam

Introduce deterministic multi-intent planning for selected safe task categories, still no Temporal.

### Phase 4D — Runtime Orchestration Design

Only here revisit Temporal or durable orchestration. This needs a separate architecture review and explicit 狗哥 approval.

---

## Approval Gate

Stop here after saving this plan. Do not implement code from this plan until 狗哥 explicitly approves execution.

Recommended handoff prompt:

```text
Plan complete and saved. Ready to execute Phase 4A: FlowWeaver gateway contract seam. Shall I proceed?
```
