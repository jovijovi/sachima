# FlowWeaver Phase 5C Runtime Client / MCP Tool Implementation Plan

> **For Hermes:** This document is the Phase 5C design gate. Do not write implementation code until the user explicitly approves this plan. After approval, use `subagent-driven-development` task-by-task with TDD and independent review.

**Goal:** Build a narrow, default-off runtime client and MCP-facing tool surface for the local FlowWeaver Temporal POC, so Hermes can start/query/update a durable transaction without shelling out to Temporal or touching Gateway production wiring.

**Architecture:** Keep the actual runtime client and tool contract under prototype scope first. Expose an optional stdio MCP server that operators may configure explicitly later; do not register a new production Hermes toolset in Phase 5C, because registry plugin toolsets can be pulled into `all`/`*` tool resolution. Reuse Phase 5B safe payload validators, local-only Temporal connection guard, validated Updates, Query snapshots, and history no-leak invariants.

**Tech Stack:** Python, existing Phase 5B `flowweaver_temporal_poc` prototype, optional `temporalio`, optional `mcp`, pytest, `scripts/run_tests.sh`.

---

## Current Baseline

- Canonical repo: `/home/ubuntu/workspace/hermes/repo/sachima`
- Feature worktree: `/home/ubuntu/workspace/hermes/worktrees/sachima/feat-flowweaver-phase5c-runtime-client-mcp-tool`
- Base branch: `feature/sachima-channel`
- Base commit: `e681d4f81f4550116fec77c3a1e3dcb7f536e1d8` (Phase 5B PR #28 merge)
- Phase 5B is merged and local worktree/branch cleanup is complete.
- Existing canonical untracked items are unrelated and must not be swept into this phase:
  - `.hermes/`
  - `docs/plans/2026-04-24-sachima-channel.md`
  - `docs/superpowers/`

## Scope Boundary

### In scope

1. Prototype-only runtime client facade for the existing Phase 5B Temporal POC.
2. Pure MCP tool contract/adapter with safe request and result schemas.
3. Optional stdio MCP server module under prototype scope.
4. Unit tests using fake clients/handles for tool contract and runtime client behavior.
5. Optional local Temporal integration tests using the same test-environment pattern as Phase 5B.
6. Documentation and dev log updates for Phase 5C.

### Out of scope for Phase 5C

1. No Gateway runtime wiring.
2. No changes to `gateway/run.py`.
3. No platform adapter changes.
4. No changes to `run_agent.py`.
5. No production service/daemon/Docker startup.
6. No edits to `~/.hermes/config.yaml` or automatic `mcp_servers` registration.
7. No production Hermes `tools/` registration unless a later approval explicitly expands scope.
8. No real credentials, connection strings, private platform payloads, or raw user/platform IDs in fixtures, docs, logs, tool outputs, or Temporal history.
9. No payload-carrying Temporal Signals.

## Design Decision: MCP-facing prototype first, not a production native tool

Phase 5C should **not** add a self-registering `tools/flowweaver_runtime_tool.py` yet.

Reason: current tool discovery and toolset resolution make plugin toolsets discoverable through the registry, and `all`/`*` expands across available toolsets. Even a narrow production tool can accidentally widen the agent-visible surface unless the check function and toolset behavior are perfectly guarded. That is doable later, but Phase 5C is the wrong time to bet runtime safety on global tool-surface behavior.

Instead, Phase 5C lands a prototype MCP stdio server and a pure adapter:

```text
agent/manual MCP config (future, explicit) -> stdio MCP server -> safe tool adapter -> runtime client -> local Temporal POC
```

This gives us the API shape and safety tests without changing default Hermes/Gateway behavior.

## Proposed Files

### Create

- `prototypes/flowweaver_phase5c_runtime_client/pyproject.toml`
- `prototypes/flowweaver_phase5c_runtime_client/README.md`
- `prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/__init__.py`
- `prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/contracts.py`
- `prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/runtime_client.py`
- `prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/tool_adapter.py`
- `prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/mcp_server.py`
- `tests/prototypes/test_flowweaver_phase5c_runtime_client_contract.py`
- `tests/prototypes/test_flowweaver_phase5c_tool_adapter.py`
- `tests/prototypes/test_flowweaver_phase5c_tool_surface.py`
- `tests/prototypes/test_flowweaver_phase5c_mcp_server_surface.py`
- `tests/integration/test_flowweaver_phase5c_runtime_client_temporal.py`

### Modify

- `docs/dev_log/2026-05-05-flowweaver-phase5c-runtime-client-mcp-tool.md`
- Potentially `prototypes/flowweaver_phase5b_temporal_poc/src/flowweaver_temporal_poc/client.py` only if reusing its client helper requires tiny reusable functions. Prefer adding Phase 5C wrappers outside Phase 5B unless duplication becomes worse than the import edge.

### Must not modify

- `gateway/run.py`
- `run_agent.py`
- `gateway/platforms/**`
- Gateway production wiring files
- `model_tools.py`
- `toolsets.py`
- `tools/registry.py`
- `tools/mcp_tool.py`
- `~/.hermes/config.yaml`

## Runtime Operations Contract

The adapter should expose a deliberately small operation set:

1. `start_transaction`
   - Input: already-safe ingress envelope or safe start payload fields accepted by Phase 5B validators.
   - Output: safe workflow ID, transaction ID, status summary; `transaction_id` is an allowed top-level safe field when produced from the safe start payload.
2. `query_snapshot`
   - Input: validated runtime workflow ID.
   - Output: Phase 5B snapshot reduced through `snapshot_to_safe_dict()` and then passed through a Phase 5C whitelist sanitizer before any tool/MCP response.
3. `record_delivery_ack`
   - Input: validated workflow ID and safe delivery ACK update.
   - Output: safe update result.
4. `approve_intent`
   - Input: validated workflow ID and safe human decision update.
   - Output: safe update result.
5. `reject_intent`
   - Input: validated workflow ID and safe human decision update.
   - Output: safe update result.
6. `cancel_transaction`
   - Input: validated workflow ID and safe cancellation update.
   - Output: safe update result.
7. `resume_after_user_input`
   - Input: validated workflow ID and safe resume update using claim-check references only.
   - Output: safe update result.

All operation names should be closed-set strings, not arbitrary method names. The adapter must never dispatch a user-provided string with `getattr()`.

## Safety Invariants

1. Default-off: no runtime tool appears in default Hermes/Gateway behavior.
2. Explicit local endpoint only: local Temporal address must pass the existing local-only validator.
3. No service lifecycle side effects: client helpers connect/call only; they do not start Docker, Temporal CLI, daemon processes, workers, or Gateway.
4. No raw payload in tool output: tool results expose status, IDs, counts, kinds, and claim-check refs only.
5. Output sanitizer required: Phase 5C must whitelist nested snapshot/update/result fields and reject or strip raw/private keys such as `raw_payload`, `tool_output`, `platform_payload`, `chat_id`, `user_id`, credentials, and connection strings before returning MCP/tool-visible data.
6. No private marker smuggling: workflow IDs, event IDs, delivery keys, and claim refs reuse Phase 5B validation and reject embedded private/platform markers.
7. Validated Updates only: all state-changing events use Temporal Updates with validators.
8. Queries are read-only: `query_snapshot` must not mutate workflow state.
9. History no-leak: integration tests inspect both rendered history JSON and serialized raw event bytes.
10. Stdio MCP only: `mcp_server.py` must not open HTTP listeners or bind ports in Phase 5C.
11. Optional dependencies only: importing the package without `temporalio` or `mcp` should fail gracefully in paths that require those extras, not at general contract import time.

## Implementation Tasks After Approval

### Task 1: Add RED tests for default-off/tool-surface boundaries

**Objective:** Prove Phase 5C does not widen production tool visibility.

**Files:**
- Create: `tests/prototypes/test_flowweaver_phase5c_tool_surface.py`

**Tests to add:**
- Assert no Phase 5C diff changes `model_tools.py`, `toolsets.py`, `tools/registry.py`, `tools/mcp_tool.py`, `run_agent.py`, `gateway/run.py`, `gateway/platforms/**`, or production Gateway wiring.
- Assert no new file under `tools/` registers a FlowWeaver runtime tool.
- Assert no code writes `mcp_servers` config.
- Implement the changed-file check against the merge-base/base branch, not only `git diff`, so the guard still works after commit.

**Run:**

```bash
scripts/run_tests.sh tests/prototypes/test_flowweaver_phase5c_tool_surface.py -q
```

**Expected guard behavior:** this boundary test may pass before implementation because it protects forbidden surfaces rather than proving a missing module. If it fails, stop and fix the plan or implementation before writing more code.

### Task 2: Add RED tests for pure request/result contract

**Objective:** Define the safe MCP-facing request/result schema before implementation.

**Files:**
- Create: `tests/prototypes/test_flowweaver_phase5c_runtime_client_contract.py`

**Tests to add:**
- Closed-set operation validation.
- Plain `dict`/`list`/primitive copying only; hostile Mapping and mutable equality objects must not influence post-validation output.
- Reject private/platform-shaped markers embedded in workflow IDs, event IDs, delivery keys, and claim refs.
- Reject raw text/output/payload fields at the adapter boundary.
- Result envelopes contain only safe fields: `ok`, `operation`, `workflow_id`, `transaction_id`, `status`, `snapshot`, `error_code`.
- Nested `snapshot`, update-result, and status objects must be whitelisted recursively; fake safe-looking dicts containing `raw_payload`, `tool_output`, `platform_payload`, `chat_id`, `user_id`, credential-shaped keys, or connection strings must not be returned.

**Run:**

```bash
scripts/run_tests.sh tests/prototypes/test_flowweaver_phase5c_runtime_client_contract.py -q
```

**Expected RED:** import/module missing.

### Task 3: Implement `contracts.py`

**Objective:** Add safe dataclasses/helpers without importing Temporal or MCP.

**Files:**
- Create: `prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/contracts.py`

**Implementation notes:**
- Keep this module dependency-light: stdlib only plus Phase 5B payload validators if needed.
- Use exact type checks where safety matters.
- Convert unsafe exceptions to stable error codes.
- Do not include raw exception strings in tool-visible results.
- Implement a Phase 5C output sanitizer/whitelist that is stricter than Phase 5B `snapshot_to_safe_dict()`, because Phase 5B currently guarantees plain-copy shape rather than nested redaction.
- Add import smoke coverage proving `flowweaver_runtime_client` and `contracts.py` import without importing `temporalio`, `mcp`, or Phase 5B runtime client/workflow modules.

**Run:**

```bash
scripts/run_tests.sh tests/prototypes/test_flowweaver_phase5c_runtime_client_contract.py -q
python -m py_compile prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/contracts.py
```

**Expected GREEN:** contract tests pass.

### Task 4: Add RED tests for runtime client calls with fake Temporal handles

**Objective:** Specify the client facade without needing a running Temporal service.

**Files:**
- Create: `tests/prototypes/test_flowweaver_phase5c_tool_adapter.py`

**Tests to add:**
- `start_transaction` calls `start_workflow` with `FlowWeaverTransactionWorkflow.run`, validated payload, task queue, and validated workflow ID.
- `query_snapshot` calls the workflow query and returns only Phase 5C-sanitized safe output, not raw `snapshot_to_safe_dict()` pass-through.
- Fake Temporal snapshots/update results containing `raw_payload`, `tool_output`, `platform_payload`, `chat_id`, `user_id`, credential-shaped keys, or connection strings are rejected or stripped before adapter output.
- Each state-changing operation calls the matching validated Update method.
- The local Temporal endpoint must be supplied explicitly to the facade/adapter/server path; omitting it must not silently default to `localhost:7233`.
- Client facade never shells out, starts services, starts workers, or reads real config.
- Runtime errors become safe error codes without leaking raw exception content.

**Run:**

```bash
scripts/run_tests.sh tests/prototypes/test_flowweaver_phase5c_tool_adapter.py -q
```

**Expected RED:** client facade missing.

### Task 5: Implement `runtime_client.py` and `tool_adapter.py`

**Objective:** Wire the pure adapter to the Phase 5B workflow/client helpers.

**Files:**
- Create: `prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/runtime_client.py`
- Create: `prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/tool_adapter.py`

**Implementation notes:**
- `runtime_client.py` may import `temporalio` and Phase 5B `client.py`/`workflows.py` only inside runtime paths, not package root or contract import paths.
- All update names should be explicit method calls, not arbitrary dynamic dispatch.
- `tool_adapter.py` should be the only boundary that accepts MCP-style dictionaries.
- Output should be deterministic JSON-compatible dicts after the Phase 5C whitelist sanitizer.
- Local Temporal endpoint injection must be explicit constructor/argument data; no ambient config read or implicit default endpoint.

**Run:**

```bash
scripts/run_tests.sh \
  tests/prototypes/test_flowweaver_phase5c_runtime_client_contract.py \
  tests/prototypes/test_flowweaver_phase5c_tool_adapter.py \
  -q
python -m py_compile \
  prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/contracts.py \
  prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/runtime_client.py \
  prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/tool_adapter.py
```

**Expected GREEN:** unit tests and py_compile pass.

### Task 6: Add optional stdio MCP server wrapper

**Objective:** Expose the adapter through MCP without changing Hermes global tool registration.

**Files:**
- Create: `prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/mcp_server.py`

**Design:**
- Use optional `mcp` SDK only inside this module.
- Provide one tool, `flowweaver_runtime`, with a closed-set `operation` field, or a tiny set of explicit tools if MCP schema support makes that safer.
- Do not auto-run on import.
- `main()` may run stdio only when invoked directly.
- No HTTP transport, SSE transport, streamable-http transport, port binding, resources, prompts, or config writes.
- Expose exactly `flowweaver_runtime` unless the implementation plan is amended and re-approved.

**Surface tests to add:**
- Importing `mcp_server.py` does not auto-run a server or mutate config.
- The server path is stdio-only; no HTTP/SSE/streamable-http listener or port binding appears in runtime code.
- The MCP surface exposes exactly `flowweaver_runtime` and no resources/prompts unless separately approved.
- No code writes `mcp_servers` config.

**Run:**

```bash
scripts/run_tests.sh tests/prototypes/test_flowweaver_phase5c_mcp_server_surface.py -q
python -m py_compile prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/mcp_server.py
```

**Expected GREEN:** surface tests and compile pass whether or not the MCP server is actually started.

### Task 7: Add Temporal integration coverage

**Objective:** Prove the client facade works against the Phase 5B workflow and preserves history no-leak behavior.

**Files:**
- Create: `tests/integration/test_flowweaver_phase5c_runtime_client_temporal.py`

**Tests to add:**
- Start a local test workflow through the Phase 5C client facade.
- Query snapshot through the facade.
- Record ACK / decision / cancel / resume updates through the facade.
- Fetch Temporal history and scan rendered JSON plus serialized raw event bytes for forbidden material.
- Confirm no Signals are used for payload-carrying events.
- Add a negative-path test where hostile adapter input is rejected before Temporal and confirm rejected raw/private material does not enter tool output or Temporal history.

**Run:**

```bash
python -m pytest tests/integration/test_flowweaver_phase5c_runtime_client_temporal.py -m integration -o 'addopts=' -q
```

**Expected GREEN:** integration passes when optional Temporal dependencies are installed.

### Task 8: Documentation and dev log update

**Objective:** Record the final implementation boundary, commands, and evidence.

**Files:**
- Modify: `prototypes/flowweaver_phase5c_runtime_client/README.md`
- Modify: `docs/dev_log/2026-05-05-flowweaver-phase5c-runtime-client-mcp-tool.md`
- Modify: this plan only if implementation deviates and the deviation is approved.

**Must record:**
- RED/GREEN evidence.
- Any skipped optional integration and why.
- No Gateway restart/service start.
- No production tool registration.
- Forbidden surface scan results.
- Independent reviewer findings and fixes.

## Verification Gates

Run before PR:

```bash
scripts/run_tests.sh \
  tests/prototypes/test_flowweaver_phase5b_temporal_payloads.py \
  tests/prototypes/test_flowweaver_phase5c_runtime_client_contract.py \
  tests/prototypes/test_flowweaver_phase5c_tool_adapter.py \
  tests/prototypes/test_flowweaver_phase5c_tool_surface.py \
  tests/prototypes/test_flowweaver_phase5c_mcp_server_surface.py \
  -q

python -m pytest \
  tests/integration/test_flowweaver_phase5b_temporal_workflow.py \
  tests/integration/test_flowweaver_phase5c_runtime_client_temporal.py \
  -m integration -o 'addopts=' -q

python -m py_compile \
  prototypes/flowweaver_phase5b_temporal_poc/src/flowweaver_temporal_poc/client.py \
  prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/__init__.py \
  prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/contracts.py \
  prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/runtime_client.py \
  prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/tool_adapter.py \
  prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/mcp_server.py

git diff --check
```

Custom scans before PR:

1. Forbidden surface scan: fail if final diff against the merge-base/base branch touches Gateway runtime wiring, `gateway/run.py`, `run_agent.py`, `gateway/platforms/**`, `model_tools.py`, `toolsets.py`, `tools/registry.py`, `tools/mcp_tool.py`, or `~/.hermes/config.yaml`.
2. Tool exposure scan: fail if Phase 5C registers a production Hermes tool, adds default MCP config, exposes MCP resources/prompts, or exposes tools outside the approved `flowweaver_runtime` surface.
3. Service lifecycle scan: fail on Docker/service/daemon/worker start calls in Phase 5C code paths.
4. Temporal signal scan: fail on payload-carrying Signal usage.
5. Sensitive material scan: fail on credential-shaped strings, raw platform payload fixtures, or private IDs in docs/tests/code.
6. Temporal history no-leak scan: integration tests must check rendered JSON and serialized raw event bytes.
7. Tool output no-leak scan: unit tests must check nested snapshots/update results for raw/private fields and credential-shaped keys before any MCP/tool response leaves the adapter.

## Review Gates

Before asking for implementation approval:

- Independent plan/spec review: check phase sequencing, scope, and whether implementation tasks are clear enough.
- Independent security/low-intrusion review: check MCP tool surface, Temporal history, no-leak, and forbidden surfaces.

Before PR after implementation:

- Independent code/spec review.
- Independent security review focused on MCP boundary, Temporal update/query calls, and output redaction.

## PR / Merge Boundary

After implementation approval, routine actions covered by scope approval:

- Write files listed in this plan.
- Run focused tests, integration tests, py_compile, diff checks, and custom scans.
- Commit, push feature branch, and open/update PR.
- Local post-merge cleanup after the user says the PR is merged or asks to merge and clean up.

Requires separate explicit approval:

- Merge PR if user has not clearly said to merge.
- Delete remote branches.
- Start/restart Gateway or any service.
- Start Docker/daemon/Temporal service outside test environments.
- Touch forbidden surfaces listed above.
- Add production Hermes tool registration.
- Edit real runtime config or credentials.

## Open Questions for Implementation Approval

1. Keep Phase 5C strictly prototype MCP-only as planned, or allow a default-off production native tool shim in the same PR? My recommendation: **prototype MCP-only now**.
2. Should Phase 5C keep all new runtime client code in a new prototype package, or extend the Phase 5B prototype package directly? My recommendation: **new Phase 5C package that imports Phase 5B helpers**, so phase boundaries stay visible.
3. Should the MCP server expose one closed-set operation tool or multiple explicit MCP tools? My recommendation: **one closed-set tool first** to centralize validation and keep schema drift small; split later only if tool ergonomics suffer.

## Approval Handoff

Plan complete means only design is approved for review. Implementation starts only after the user explicitly approves Phase 5C execution.
