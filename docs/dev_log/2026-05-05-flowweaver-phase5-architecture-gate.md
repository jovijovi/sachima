# FlowWeaver Phase 5 — Architecture Gate Dev Log

Timestamp: 2026-05-05 11:48:13 CST +0800

## Scope

Enter Phase 5 by creating an architecture gate for FlowWeaver durable runtime / Temporal adoption.

This phase is design-gate only. It should decide the safe next landing seam after Phase 4A-4H and document the implementation sequence. It must not implement runtime code, start Temporal, start Docker, perform runtime wiring, mutate platform adapters, change visible IM behavior, or do any Gateway restart.

## Branch and worktree

```text
branch: feat/flowweaver-phase5-architecture-gate
worktree: /home/ubuntu/workspace/hermes/worktrees/sachima/feat-flowweaver-phase5-architecture-gate
base: origin/feature/sachima-channel @ de1ed6b85206cbcaa6ff223ef7fce764669b915a
```

Canonical repo before branching:

```text
path: /home/ubuntu/workspace/hermes/repo/sachima
branch: feature/sachima-channel
open PRs on base: []
canonical/origin: synced at de1ed6b85206cbcaa6ff223ef7fce764669b915a
```

Canonical had existing local untracked items outside this worktree:

```text
.hermes/
docs/plans/2026-04-24-sachima-channel.md
docs/superpowers/
```

These were not copied into the Phase 5 worktree and are not part of this phase.

## Baseline verification

Command:

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
142 passed in 18.32s
```

## Context inspected

```text
AGENTS.md
docs/plans/2026-05-05-flowweaver-phase4h-gateway-shadow-dry-run.md
docs/dev_log/2026-05-05-flowweaver-phase4h-gateway-shadow-dry-run.md
docs/plans/2026-05-04-flowweaver-phase4g-mock-durable-consumer.md
gateway/flowweaver_contract.py
gateway/flowweaver_shadow.py
gateway/flowweaver_mock_durable.py
gateway/flowweaver_shadow_dry_run.py
gateway/progress/events.py
gateway/progress/store.py
gateway/run.py FlowWeaver config and final shadow capture seam
```

Current-doc check:

```text
Context7 resolved Temporal Python SDK as /temporalio/sdk-python.
Context7 Temporal Python SDK docs confirmed run/signal/query workflow patterns, client.start_workflow with id/task_queue, and activity execution with timeouts/retry policy.
Context7 Temporal docs confirmed Continue-As-New / event-history concern as a future design gate.
```

## Planned files

Allowed files for this design-only phase:

```text
docs/plans/2026-05-05-flowweaver-phase5-architecture-gate.md
docs/dev_log/2026-05-05-flowweaver-phase5-architecture-gate.md
```

Explicitly not planned in this phase:

```text
run_agent.py
model_tools.py
toolsets.py
cli.py
hermes_cli/*
gateway/run.py
gateway/platforms/*
gateway/flowweaver_runtime_contract.py
tests/gateway/*
no Temporal / no Docker / no daemon / no service / no persistence / no runtime wiring / no Gateway restart
```

## Design status

Plan drafted:

```text
docs/plans/2026-05-05-flowweaver-phase5-architecture-gate.md
```

Phase 5 gate recommendation:

```text
Do not wire Temporal directly into the live Gateway yet.
Proceed next to Phase 5A Durable Runtime Ingress Contract after explicit approval.
Keep Phase 5A pure, in-memory, no Temporal import, no runtime wiring, no persistence, no Gateway restart.
Enter Temporal only in Phase 5B as a local prototype under prototypes/, still without Gateway wiring.
```

Reasoning:

```text
Phase 4H proves the Gateway lifecycle can execute safe shadow/corpus/mock-durable dry-run logic without visible side effects.
It does not yet prove that a runtime ingress envelope is exact-shape, claim-check-aware, idempotent, or ready for Temporal event history.
Connecting Temporal now would persist an under-specified contract.
```

## Verification before design handoff

Planned checks:

```bash
git check-ignore -v \
  docs/plans/2026-05-05-flowweaver-phase5-architecture-gate.md \
  docs/dev_log/2026-05-05-flowweaver-phase5-architecture-gate.md || true
git add -N docs/plans/2026-05-05-flowweaver-phase5-architecture-gate.md docs/dev_log/2026-05-05-flowweaver-phase5-architecture-gate.md
git diff --check -- docs/plans/2026-05-05-flowweaver-phase5-architecture-gate.md docs/dev_log/2026-05-05-flowweaver-phase5-architecture-gate.md
python doc marker / allowed-file / forbidden-runtime / sensitive scan
```

Independent plan reviews planned:

```text
spec / architecture consistency review
security / no-leak / low-intrusion review
```

Initial independent plan review results:

```text
spec / architecture consistency review: PASS — no concrete blockers.
security / no-leak review: BLOCKER — Decision 4 claim-check wording could be read as allowing raw prompts/outputs/card JSON/media paths/platform payloads to be claim-check persisted; Phase 5B wording also said claim_check_write/read and claim-checked payloads too loosely.
```

Patch applied after blocker:

```text
- Retitled Decision 4 to "Only claim-check references may cross durable boundaries".
- Changed claim-check wording so durable signals/updates/start payloads carry only opaque sanitized refs plus safe metadata.
- Listed raw snapshot/capture/full agent_result, raw prompts, raw command/stdout/stderr/tool outputs, card JSON, media bytes/paths, platform payloads, platform/chat/user/message IDs, raw delivery ACK payloads/IDs, credentials, tokens, and secrets as forbidden material.
- Replaced Phase 5B `claim_check_write/read` with `validate_claim_check_ref`.
- Replaced "claim-checked payloads" with "already-sanitized envelopes or claim-check references only".
```

Final verification and review results after rerun:

```text
git check-ignore: no planned doc files ignored
git diff --check: passed
doc marker / allowed-file / forbidden-runtime / sensitive scan: passed
spec / architecture consistency review: PASS — no concrete blockers remain
security / no-leak review: PASS — previous claim-check blocker fixed; no new blocker
```
