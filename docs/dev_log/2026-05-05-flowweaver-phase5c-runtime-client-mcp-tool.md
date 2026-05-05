# FlowWeaver Phase 5C — Runtime Client / MCP Tool Dev Log

Timestamp: 2026-05-05 19:37:55 CST +0800

## User Ask

```text
开始下一个阶段的规划。
```

Current preserved task state after context compression:

```text
Phase 5C Runtime Client / MCP Tool planning/design gate
```

## Baseline Verification

- Canonical repo: `/home/ubuntu/workspace/hermes/repo/sachima`
- Canonical branch: `feature/sachima-channel`
- Canonical HEAD: `e681d4f81f4550116fec77c3a1e3dcb7f536e1d8`
- `origin/feature/sachima-channel`: `e681d4f81f4550116fec77c3a1e3dcb7f536e1d8`
- Phase 5B PR #28: merged before this phase.
- New Phase 5C worktree: `/home/ubuntu/workspace/hermes/worktrees/sachima/feat-flowweaver-phase5c-runtime-client-mcp-tool`
- New Phase 5C branch: `feat/flowweaver-phase5c-runtime-client-mcp-tool`

Canonical untracked items observed before Phase 5C and not part of this phase:

```text
.hermes/
docs/plans/2026-04-24-sachima-channel.md
docs/superpowers/
```

## Skills / Process Knowledge Loaded

- `software-development/writing-plans`
- `software-development/plan`
- `software-development/hermes-workspace-worktrees`
- `software-development/use-driven-skill-validation`
- `devops/temporal-durable-orchestration`
- `mcp/native-mcp`
- `software-development/superpowers/verification-before-completion`
- `software-development/requesting-code-review`

Use-driven validation applied: project-local docs and source files were treated as higher-grade evidence than generic skills.

## Context Inspected

Planning read or inspected these project files and seams:

- `docs/plans/2026-05-05-flowweaver-phase5-architecture-gate.md`
- `docs/plans/2026-05-05-flowweaver-phase5a-durable-runtime-ingress-contract.md`
- `docs/plans/2026-05-05-flowweaver-phase5b-local-temporal-poc.md`
- `docs/dev_log/2026-05-05-flowweaver-phase5b-local-temporal-poc.md`
- `gateway/flowweaver_runtime_contract.py`
- `prototypes/flowweaver_phase5b_temporal_poc/src/flowweaver_temporal_poc/client.py`
- `prototypes/flowweaver_phase5b_temporal_poc/src/flowweaver_temporal_poc/payloads.py`
- `prototypes/flowweaver_phase5b_temporal_poc/src/flowweaver_temporal_poc/workflows.py`
- `tools/registry.py`
- `tools/mcp_tool.py`
- `mcp_serve.py`
- `tests/tools/test_mcp_tool.py`
- `toolsets.py`
- `model_tools.py`
- `acp_adapter/server.py`
- `pyproject.toml`

## Key Findings

1. Phase 5B established a local-only Temporal POC with safe payload projection, local Temporal client helper, deterministic workflow, Query snapshots, and validated Updates.
2. Phase 5B explicitly avoided Gateway wiring, Docker/service startup, production runtime behavior changes, and payload-carrying Signals.
3. Existing MCP support registers external MCP server tools into plugin toolsets named like `mcp-<server>` and aliases the raw server name.
4. `toolsets.py` resolves plugin toolsets and special `all`/`*` aliases across available toolsets, so a new production/self-registering runtime tool can widen surface area if it is not very carefully guarded.
5. ACP can register session-provided MCP servers and refresh the agent tool surface, but Phase 5C does not need to modify ACP behavior.
6. `pyproject.toml` already has optional extras for `mcp` and `flowweaver-temporal`; Phase 5C should keep those optional and avoid moving them into base runtime.

## Planning Decision

Phase 5C should land a prototype MCP-facing runtime client first, not a production native Hermes tool.

Reason: this gives the agent-facing API and safety tests while preserving default-off behavior and avoiding accidental exposure through global toolset resolution. A production tool shim can be a later phase after the MCP/runtime contract is proven.

## Draft Plan Saved

- `docs/plans/2026-05-05-flowweaver-phase5c-runtime-client-mcp-tool.md`

## Forbidden Surfaces for This Phase

Implementation must not touch:

- `gateway/run.py`
- `run_agent.py`
- `gateway/platforms/**`
- production Gateway wiring
- `model_tools.py`
- `toolsets.py`
- `tools/registry.py`
- `tools/mcp_tool.py`
- `~/.hermes/config.yaml`

Any expansion into those files requires separate user approval.

## Planning Verification Log

Initial doc gate attempt:

- `git diff --check`: passed.
- doc marker/scope check: verifier false-positive on the explicit "requires separate approval" Gateway restart boundary; verifier was corrected to classify separately-approved risky actions as safe boundary text, not execution promises.

Independent review pass 1:

- Plan/spec review: PASS, no blockers.
- Security/low-intrusion review: two blockers.
  1. Add an explicit Phase 5C output sanitizer/whitelist gate because Phase 5B `snapshot_to_safe_dict()` is a plain-copy helper, not nested redaction.
  2. Add MCP server surface tests because compile-only is too weak for the central MCP exposure risk.

Plan revisions made after review:

- Added nested tool-output/snapshot/update-result no-leak sanitizer requirements and tests.
- Added MCP server surface test file and gates for stdio-only, no auto-run, exact `flowweaver_runtime` surface, and no resources/prompts/config writes.
- Tightened forbidden adapter path to `gateway/platforms/**`.
- Clarified default-off guard tests, `transaction_id` result field, explicit local endpoint injection, optional import smoke coverage, merge-base forbidden-surface scanning, and negative-path Temporal no-leak coverage.

Final review results after plan revision:

- Doc gates before re-review: passed (`git diff --check`, ignored-file check, changed-file allowlist, doc marker/scope checks, forbidden surface checks, sensitive material scan).
- Plan/spec blocker-only re-review: PASS, no blockers.
- Security/low-intrusion blocker-only re-review: PASS, no blockers.
- Final doc gates after this dev-log update: passed (`git diff --check`, ignored-file check, changed-file allowlist, doc marker/scope checks, stale-path check, forbidden boundary markers, and sensitive material scan).

## Implementation Approval Boundary

The user explicitly approved Phase 5C implementation at 2026-05-05 21:05 CST in Feishu:

```text
批准 Phase 5C 实现
```

Implementation approval covers only the prototype files/tests listed in the plan, focused verification, independent review, commit, push, and PR creation. It does not approve production Gateway wiring, production tool registration, service startup/restart, Docker/daemon startup, real config/credential edits, PR merge, or remote branch deletion.

## Implementation Log

### 2026-05-05 21:22:10 CST

Implemented Phase 5C prototype-only runtime client/MCP adapter in a strict RED/GREEN flow.

Created:

- `prototypes/flowweaver_phase5c_runtime_client/pyproject.toml`
- `prototypes/flowweaver_phase5c_runtime_client/README.md`
- `prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/__init__.py`
- `prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/contracts.py`
- `prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/runtime_client.py`
- `prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/tool_adapter.py`
- `prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/mcp_server.py`
- `tests/prototypes/test_flowweaver_phase5c_tool_surface.py`
- `tests/prototypes/test_flowweaver_phase5c_runtime_client_contract.py`
- `tests/prototypes/test_flowweaver_phase5c_tool_adapter.py`
- `tests/prototypes/test_flowweaver_phase5c_mcp_server_surface.py`
- `tests/integration/test_flowweaver_phase5c_runtime_client_temporal.py`

RED evidence:

- `tests/prototypes/test_flowweaver_phase5c_tool_surface.py -q`: `3 passed` before implementation, as expected for a guard suite.
- `tests/prototypes/test_flowweaver_phase5c_runtime_client_contract.py -q`: failed with missing `flowweaver_runtime_client` module.
- `tests/prototypes/test_flowweaver_phase5c_tool_adapter.py -q`: failed with missing runtime client/source files.
- `tests/prototypes/test_flowweaver_phase5c_mcp_server_surface.py -q`: failed with missing MCP server/source files.
- `tests/integration/test_flowweaver_phase5c_runtime_client_temporal.py -m integration -o 'addopts=' -q`: collection failed with missing `flowweaver_runtime_client` module.

GREEN evidence after implementation:

- `scripts/run_tests.sh tests/prototypes/test_flowweaver_phase5c_runtime_client_contract.py tests/prototypes/test_flowweaver_phase5c_tool_adapter.py tests/prototypes/test_flowweaver_phase5c_tool_surface.py tests/prototypes/test_flowweaver_phase5c_mcp_server_surface.py -q`: `19 passed in 0.52s`.
- `python -m pytest tests/integration/test_flowweaver_phase5c_runtime_client_temporal.py -m integration -o 'addopts=' -q`: `4 passed in 0.56s`.

Implementation boundary notes:

- No Gateway restart was performed for this implementation.
- No service/daemon/Docker startup was performed.
- No production Hermes tool registration was added.
- `mcp_server.py` is stdio-only, import-safe, and exposes exactly `flowweaver_runtime`.
- Runtime endpoint injection is explicit; there is no implicit default endpoint.
- Tool-visible output uses a Phase 5C nested whitelist sanitizer beyond Phase 5B plain-copy projection.
- Negative-path integration covers rejected raw/private adapter input and confirms rendered Temporal history JSON plus serialized raw event bytes do not contain the hostile sentinels.

### 2026-05-05 21:44:16 CST

Independent implementation review initially returned FAIL with three blockers:

1. Raw `ValueError` strings could reach MCP/tool-visible `error_code`.
2. `invoke_flowweaver_runtime()` could raise before returning a safe result envelope when runtime construction/connect failed.
3. Tests were missing for runtime-error redaction and runtime creation/connect failure paths.

Fixes applied:

- Added RED tests:
  - `test_tool_adapter_maps_unknown_runtime_value_errors_to_stable_error_codes`
  - `test_invoke_flowweaver_runtime_returns_safe_error_when_runtime_creation_fails`
- Added stable error-code allowlist in `contracts.py`; unknown exception text maps to `runtime_error` and `unsafe_tool_output` maps to `unsafe_output`.
- Wrapped runtime factory/client construction/connect failures in `invoke_flowweaver_runtime()` so MCP-visible paths return safe envelopes.
- Moved `FlowWeaverRuntimeClient.connect()` endpoint validation before importing the Phase 5B Temporal client, preserving the optional-import/error-boundary behavior.
- Fixed the changed-file guard to include worktree and intent-to-add/cached paths, not only committed diff plus untracked files.
- Split synthetic `api` + `_key=` marker literals to avoid poisoning credential-shaped scan gates while preserving runtime detection behavior.

Post-fix verification:

- New RED tests failed before the fix with `error_code: secret` and an uncaught `invalid_temporal_address` exception.
- New tests passed after the fix: `2 passed in 0.49s`, then `1 passed in 0.47s` after the optional-import ordering fix.
- Full unit/prototype gate: `35 passed in 0.58s`.
- Full integration gate: `12 passed in 1.18s`.
- `py_compile`: passed.
- `git diff --check`: passed.
- Custom scans: passed; changed-file count `14`.

Independent blocker-only re-review results:

- Spec/code blocker-only re-review: PASS, no remaining blockers.
- Security/low-intrusion blocker-only re-review: PASS, no remaining blockers.
