# P6-A Temporal-backed controlled AI FLOW execution implementation

Date: 2026-06-25
Branch: `feat/p6a-temporal-controlled-ai-flow-implementation`
Status: PR #169 open; local implementation verified; merge requires fresh live PR/CI/head checks and explicit approval.

## Scope

This slice implements the separately approved P6-A gate:

```text
approve_agent_run_supervisor_sachima_p6a_temporal_backed_controlled_ai_flow_execution_implementation_controlled_deterministic_or_injected_fake_steps_only_default_off_no_real_agent_execution_no_write_roles_no_live_no_gateway_no_feishu_no_production_config_no_real_delivery
```

It adds a thin, default-off P6-A composition layer that runs the existing WP4 controlled AI FLOW orchestrator through the existing P5 `StepExecutor` seam. P6-A is behavior-bearing at the orchestration/runtime seam, but still uses controlled-deterministic or injected/fake step bodies only.

## Implementation surface

New production source:

- `sachima_supervisor/p6_controlled_ai_flow.py`

New tests:

- `tests/sachima_supervisor/p6_controlled_ai_flow/unit/*`
- `tests/sachima_supervisor/p6_controlled_ai_flow/hermetic/*`
- `tests/sachima_supervisor/p6_controlled_ai_flow/_support.py`

No edits were made to WP4 implementation modules, `sachima_supervisor/p5_temporal/*`, Gateway/Feishu/platform surfaces, production config, `pyproject.toml`, or lockfiles.

## Strongest current meaning

P6-A proves that a caller can:

1. pass an exact outer P6 approval token plus `enabled=True`;
2. compose `create_workflow_run -> step_workflow_run(executor=...) -> summarize_workflow_run` using the unmodified WP4 entrypoints;
3. inject either the existing P5 local/offline oracle or the existing P5 Temporal `P5TemporalStepExecutor` seam;
4. run a hermetic-local Temporal Worker path with controlled-deterministic step bodies;
5. query/recover/close through caller-owned executor controls without relaunching work;
6. request cancellation while preserving WP3b active-run cancellation WATCH;
7. emit sanitized P6 evidence that carries outer `p6_*` codes plus inner WP4/runtime codes without raw material.

It does **not** prove or approve real agent execution, real acpx/npx/Claude/Codex step bodies, write roles, live/Gateway/Feishu/IM behavior, production cluster/traffic, production config writes, or real delivery.

## Core design

`p6_controlled_ai_flow.py` adds:

- `P6_CONTROLLED_AI_FLOW_EXECUTION_APPROVAL_TOKEN`
- additive outer stable codes:
  - `p6_execution_disabled`
  - `p6_approval_mismatch`
  - `p6_precondition_unmet`
  - `p6_gate_blocked`
- `evaluate_p6_admission(...)`, a pure zero-runtime-call admission gate;
- `build_p6_evidence_projection(...)`, a SCAN-1 guarded allowlist evidence projection;
- `P6ControlledAiFlowSession`, which composes WP4 + injected executor operations:
  - `create_run`
  - `step`
  - `run_linear`
  - `query`
  - `cancel`
  - `recover`
  - `close`

The outer `p6_*` code family wraps but never replaces inner `runtime_*` or WP4 activity codes.

## TDD / implementation provenance

Claude Code was used as the main programmer with model `claude-opus-4-8[1m]`, effort `xhigh`, and a strict TDD prompt. Its shell execution was blocked by Claude Code permission gating (`This command requires approval`), so it produced code/tests but could not provide live test evidence.

Hermes then ran the gates. The first live P6 unit run against Claude's output produced real RED/failure evidence:

```text
uv run --frozen --extra dev python -m pytest tests/sachima_supervisor/p6_controlled_ai_flow/unit/ -q
4 failed, 37 passed in 0.40s
```

Failure classes:

- missing-executor test helper bug;
- detector teeth regex not matching `launch_claude_code()`;
- P6 cancel path reading nonexistent `CancellationRecordResult.ok`.

Hermes made narrow fixes only:

- fixed the test helper's explicit `executor=None` path;
- strengthened the boundary regex for `claude_code` variants;
- derived cancellation ok from `record.to_durable_state()["ok"]`.

GREEN after fixes:

```text
uv run --frozen --extra dev python -m pytest tests/sachima_supervisor/p6_controlled_ai_flow/unit/ -q
42 passed in 0.34s
```

## Local verification

Focused and regression gates run on 2026-06-25:

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
```

Static/scanning gates:

```text
uv run --frozen --extra dev ruff check sachima_supervisor/p6_controlled_ai_flow.py tests/sachima_supervisor/p6_controlled_ai_flow
All checks passed!

git diff --check
PASS

python tools/sync_roadmap_status.py --check --base-remote sachima
docs/roadmap/current-status.md: machine status block is up to date

changed-file allowlist
PASS — only P6 source/test/docs paths

forbidden Gateway/Feishu/platform/dependency surface scan
PASS

forbidden real-runner added-line scan
PASS

added-line secret/leak scan
PASS
```

## Test coverage added

Unit tests cover:

- exact P6 approval token;
- p6 code family distinct from runtime codes;
- disabled/mismatched/precondition/gate-blocked admission failures with zero executor calls;
- unmodified WP4 composition via P5 local/offline oracle;
- substitutable fake/oracle outcomes;
- terminal-gate parking;
- pre-step gate zero executor work;
- idempotent replay;
- failed step fail-closed behavior;
- P5TemporalStepExecutor seam reuse without reimplementing translation;
- unsafe material rejected before backend calls;
- query/recover no relaunch;
- between-step and active-run cancellation semantics;
- close evidence sanitization;
- boundary/no-real-runner/no-import scans.

Hermetic tests cover:

- real hermetic-local Temporal Worker controlled-deterministic end-to-end path;
- duplicate/divergent/recover/cancel WATCH behavior;
- three-surface no-leak/canary behavior.

## Boundaries preserved

This implementation does not approve or implement:

```text
real_acpx_or_npx_or_agent_execution
real_claude_code_or_codex_cli_step_bodies
write_capable_roles
additional_or_unbounded_persistent_session_execution
additional_or_unbounded_cancellation_execution
clean_active_run_cancellation_claims_beyond_existing_watch
gateway_involvement_or_mutation
gateway_restart_or_reload
feishu_or_im_delivery
platform_adapter_mutation
public_ingress
production_cluster_or_production_traffic
production_config_write
service_restart_or_reload
real_delivery
```

WP3b active-run cancellation WATCH remains open; P6-A propagates WATCH and must not claim clean active-run cancellation.

## Review status

Codex review history so far:

1. `--sandbox read-only` could not inspect the repo because Codex/bubblewrap failed with `bwrap: loopback: Failed RTM_NEWADDR: Operation not permitted`; this is tooling, not a code finding.
2. Fallback read-only-by-instruction review found stale roadmap wording; `docs/roadmap/current-status.md` was corrected.
3. Fallback re-review found a real control-path blocker: invalid active-run cancel and close could call executor controls before WP4 resident-state validation. P6 now validates resident run/cancel preconditions before executor controls, close summarizes before closing, and `test_control_ops_validate_resident_state_before_executor_side_effects` covers zero executor calls for missing resident state.

Final Codex exact-head blocker re-review passed after those fixes:

```text
VERDICT: PASS
SCORE: 96
BLOCKERS:
- None
```

PR #169 is open at https://github.com/jovijovi/sachima/pull/169. Merge readiness is live state and must be checked from GitHub on the current head before approval/merge; this archived plan/dev-log must not be used as live CI or merge-state authority.
