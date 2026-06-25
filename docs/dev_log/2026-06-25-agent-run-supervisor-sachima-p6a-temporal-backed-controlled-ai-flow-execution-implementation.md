# Dev log — P6-A Temporal-backed controlled AI FLOW execution implementation

Date: 2026-06-25
Branch: `feat/p6a-temporal-controlled-ai-flow-implementation`
Status: local implementation verified; Codex blocker review PASS; pending PR.

## User approval

User approved P6-A implementation with the exact phrase:

```text
approve_agent_run_supervisor_sachima_p6a_temporal_backed_controlled_ai_flow_execution_implementation_controlled_deterministic_or_injected_fake_steps_only_default_off_no_real_agent_execution_no_write_roles_no_live_no_gateway_no_feishu_no_production_config_no_real_delivery
```

The approval is explicitly limited to default-off, controlled-deterministic/injected-fake steps. It excludes real agent/acpx/npx execution, write roles, live/Gateway/Feishu, production config, and real delivery.

## Preflight

Live truth before implementation:

- PR #168 P6 pre-development governance was merged.
- `release/sachima` had open PR count 0.
- Base worktree head: `23bb5b92cbbd41258e53968dec4ec221a4136769`.
- CodeGraph initialized for the implementation worktree.
- Claude Code smoke with model `claude-opus-4-8[1m]`, effort `xhigh`, returned `CLAUDE_SMOKE_OK`.

Worktree:

```text
/home/ecs-user/workspace/hermes/worktrees/sachima/feat-p6a-temporal-controlled-ai-flow
branch: feat/p6a-temporal-controlled-ai-flow-implementation
```

## Implementation provenance

Claude Code was launched as main programmer with the exact model `claude-opus-4-8[1m]`, effort `xhigh`, and a strict TDD prompt.

Claude created the P6-A module and tests but could not run shell commands inside its session because its Bash invocations required approval. No fake test evidence was accepted from Claude.

Hermes ran the tests and verified the diff directly.

## First live failure evidence

Initial unit gate after Claude output:

```text
uv run --frozen --extra dev python -m pytest tests/sachima_supervisor/p6_controlled_ai_flow/unit/ -q
4 failed, 37 passed in 0.40s
```

Failures:

1. helper defaulted `executor=None` back to a default executor, invalidating the missing-executor precondition test;
2. boundary detector did not catch `launch_claude_code()` because the regex treated `_` as a word character;
3. `P6ControlledAiFlowSession.cancel(...)` attempted to read nonexistent `CancellationRecordResult.ok` in two tests.

Hermes made narrow fixes only:

- test helper sentinel for explicit `executor=None`;
- boundary regex strengthened for `claude_code` variants;
- cancellation `ok` derived from `record.to_durable_state()["ok"]`.

## Implemented behavior

Added `sachima_supervisor/p6_controlled_ai_flow.py` with:

- exact P6 approval token;
- additive p6 stable codes;
- pure admission helper with zero executor calls on failure;
- P6 evidence projection with SCAN-1 guard;
- `P6ControlledAiFlowSession` over unmodified WP4 + injected executor;
- caller-owned query/cancel/recover/close controls;
- active-run cancellation WATCH preservation.

Added tests under `tests/sachima_supervisor/p6_controlled_ai_flow/` for unit and hermetic gates.

## Verification

```text
uv run --frozen --extra dev python -m pytest tests/sachima_supervisor/p6_controlled_ai_flow/unit/ -q
42 passed in 0.34s

uv run --frozen --extra dev python -m pytest tests/sachima_supervisor/test_ai_flow_orchestration.py tests/sachima_supervisor/test_p5_runtime_adapter.py -q
64 passed in 0.40s

uv run --frozen --extra dev --extra flowweaver-temporal python -m pytest tests/sachima_supervisor/p6_controlled_ai_flow/hermetic/ -q
9 passed in 1.66s

uv run --frozen --extra dev --extra flowweaver-temporal python -m pytest tests/sachima_supervisor/p5_temporal/hermetic/test_determinism_replay.py -q
1 passed in 0.30s

uv run --frozen --extra dev --extra flowweaver-temporal python -m pytest tests/sachima_supervisor/p5_temporal/unit/ -q
172 passed in 2.20s

uv run --frozen --extra dev --extra flowweaver-temporal python -m pytest tests/sachima_supervisor/p6_controlled_ai_flow tests/sachima_supervisor/test_ai_flow_orchestration.py tests/sachima_supervisor/test_p5_runtime_adapter.py tests/sachima_supervisor/p5_temporal/hermetic/test_determinism_replay.py -q
116 passed in 2.35s

uv run --frozen --extra dev ruff check sachima_supervisor/p6_controlled_ai_flow.py tests/sachima_supervisor/p6_controlled_ai_flow
All checks passed!

git diff --check
PASS

python tools/sync_roadmap_status.py --check --base-remote sachima
docs/roadmap/current-status.md: machine status block is up to date
```

Custom scans:

```text
changed-file allowlist: PASS
forbidden Gateway/Feishu/platform/dependency surface scan: PASS
forbidden real-runner added-line scan: PASS
added-line secret/leak scan: PASS
```

## Safety notes

The implementation keeps these boundaries closed:

- no real acpx/npx/agent execution;
- no Claude Code or Codex CLI as P6-A step bodies;
- no write-capable roles;
- no Gateway/Feishu/platform mutation;
- no production cluster/traffic;
- no production config write;
- no real delivery.

WP3b active-run cancellation WATCH remains open and is intentionally propagated, not upgraded.

## Codex blocker review

Initial `--sandbox read-only` Codex review was blocked by the environment (`bwrap: loopback: Failed RTM_NEWADDR: Operation not permitted`). Fallback read-only-by-instruction review first found roadmap drift, then a control-path ordering blocker. Both were fixed. Final fallback re-review returned:

```text
VERDICT: PASS
SCORE: 96
BLOCKERS:
- None
```

Post-review diff checksum was unchanged across the fallback review run, confirming Codex did not modify files.

## Next steps

1. Open PR after local + review gates are clean.
2. Wait for GitHub checks and send head-SHA-bound approval card.
