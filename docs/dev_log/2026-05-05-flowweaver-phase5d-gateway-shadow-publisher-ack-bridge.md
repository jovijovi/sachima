# FlowWeaver Phase 5D — Gateway Shadow Publisher / ACK Bridge Dev Log

Timestamp: 2026-05-05 23:07:29 CST +0800

## User Ask

```text
开始下一个阶段
```

## Baseline Verification

- Canonical repo: `/home/ubuntu/workspace/hermes/repo/sachima`
- Canonical branch: `feature/sachima-channel`
- Canonical HEAD observed before creating this worktree: `ea8e6bf53008196768db24efedf21f8a585f6141`
- PR #29 / Phase 5C: `MERGED`, merge commit `ea8e6bf53008196768db24efedf21f8a585f6141`
- New Phase 5D worktree: `/home/ubuntu/workspace/hermes/worktrees/sachima/feat-flowweaver-phase5d-gateway-shadow-publisher-ack-bridge`
- New Phase 5D branch: `feat/flowweaver-phase5d-gateway-shadow-publisher-ack-bridge`
- Worktree HEAD: `ea8e6bf53008196768db24efedf21f8a585f6141`

Canonical untracked items observed before Phase 5D and not part of this phase:

```text
.hermes/
docs/plans/2026-04-24-sachima-channel.md
docs/superpowers/
```

## Skills / Process Knowledge Loaded

- `software-development/superpowers/using-superpowers`
- `software-development/hermes-workspace-worktrees`
- `software-development/plan`
- `software-development/writing-plans`
- `github/github-pr-workflow`
- `devops/temporal-durable-orchestration`
- `software-development/test-driven-development`
- `software-development/requesting-code-review`
- `software-development/use-driven-skill-validation`
- `agent-workflows/progress-feedback-policy`
- `agent-workflows/result-artifact-output-policy`
- `software-development/subagent-driven-development`

Use-driven validation applied: project-local docs/source/tests were treated as higher-grade evidence than prior session summaries or generic skill guidance.

## Context Inspected

- `docs/plans/2026-05-05-flowweaver-phase5-architecture-gate.md`
- `docs/plans/2026-05-05-flowweaver-phase5c-runtime-client-mcp-tool.md`
- `docs/dev_log/2026-05-05-flowweaver-phase5c-runtime-client-mcp-tool.md`
- `gateway/flowweaver_shadow.py`
- `gateway/flowweaver_shadow_dry_run.py`
- `gateway/flowweaver_mock_durable.py`
- `gateway/flowweaver_runtime_contract.py`
- `gateway/run.py` around the existing FlowWeaver shadow/dry-run seam
- `tests/gateway/test_flowweaver_shadow_tap.py`
- `tests/gateway/test_flowweaver_shadow_dry_run.py`
- `tests/gateway/test_flowweaver_runtime_contract.py`
- `tests/gateway/test_run_progress_topics.py`
- `prototypes/flowweaver_phase5b_temporal_poc/src/flowweaver_temporal_poc/payloads.py`
- `prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/contracts.py`
- `prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/runtime_client.py`
- `prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/tool_adapter.py`
- `tests/prototypes/test_flowweaver_phase5c_tool_adapter.py`

## Key Findings

1. The next roadmap item after Phase 5C is Phase 5D: Gateway shadow publisher / ACK bridge, default-off and no visible behavior change.
2. Existing Gateway already has a default-off shadow/dry-run seam in `gateway/run.py` that can be extended narrowly if approved.
3. Phase 5A can produce a safe runtime ingress envelope from Gateway shadow/dry-run inputs.
4. Phase 5C runtime client is prototype-only under `prototypes/` and should not become a production Gateway dependency in Phase 5D.
5. Phase 5B/5C currently use fixed POC runtime IDs (`runtime_tx_replay_corpus`, `runtime_event_start_runtime_tx_replay_corpus`). This would collide if Gateway silently started real workflows for live turns. Phase 5D must therefore remain a shadow publication/ACK bridge evidence phase, not a live Temporal publisher.
6. Delivery ACK projection must be synthetic and safe: no platform message IDs, chat/user IDs, raw adapter responses, card JSON, raw ACK payloads, or secret-shaped strings.

## Planning Decision

Phase 5D should build a pure Gateway shadow publisher/ACK bridge helper plus a tiny default-off run-loop attach hook. It should not import or call Phase 5C runtime client from Gateway, and it should not start or update real Temporal workflows.

Reason: this proves the Gateway-side request/ACK bridge contract while preserving no visible behavior change and avoiding the fixed-ID live-publish trap.

## Draft Plan Saved

- `docs/plans/2026-05-05-flowweaver-phase5d-gateway-shadow-publisher-ack-bridge.md`

## Proposed Implementation Boundary

If approved, Phase 5D implementation covers only:

- `gateway/flowweaver_shadow_publisher.py`
- `tests/gateway/test_flowweaver_shadow_publisher.py`
- `tests/gateway/test_flowweaver_shadow_publisher_run_hook.py` or a narrow extension of `tests/gateway/test_run_progress_topics.py`
- a tiny hook in `gateway/run.py` under the existing FlowWeaver shadow block
- this dev log
- focused tests, py_compile, diff checks, boundary scans, independent review, commit, push, PR creation

Still not approved without separate explicit user instruction:

- live Temporal publishing from Gateway
- importing Phase 5C runtime client from Gateway
- no starting workers/services/Docker/daemon/Temporal CLI
- no Gateway restart
- platform adapter changes
- global tool registry/toolset changes
- config writes
- real secrets or credentials
- PR merge
- remote branch deletion

## Planning Verification Log

Initial plan authored.

Initial doc gate:

- `git diff --check`: passed.
- custom doc marker/scope/changed-file/ignored-file/sensitive scan: passed after tightening the scanner to distinguish explicit no-approval lifecycle boundaries from execution promises.

Independent review pass 1:

- Plan/spec review: FAIL with two blockers.
  1. Forbidden-source scans were too broad because `gateway/run.py` already has unrelated baseline `mcp`/process/service code; scans must be diff-hunk-aware or baseline-aware.
  2. Run-hook exception logging needed an explicit sanitized-log requirement, not raw `str(exc)` debug logging.
- Security/low-intrusion review: FAIL with the same two blockers.

Plan revisions made after review:

- Replaced file-wide Gateway forbidden-source scans with merge-base/diff-hunk-aware scans that fail only on new Phase 5D additions or brand-new files.
- Added explicit stable sanitized debug logging requirements for publisher hook failures.
- Added a required `caplog` negative test where an exception contains raw IDs/secret-shaped text and must not appear in `agent_result`, adapter output, or logs.
- Clarified the false-positive scan risk around pre-existing `gateway/run.py` baseline code.

Final planning gate after blocker fixes:

- `git diff --check`: passed.
- custom doc marker/scope/changed-file/ignored-file/forbidden-boundary/sensitive scan: passed.
- blocker-only plan/spec re-review: PASS, no blockers.
- blocker-only security/low-intrusion re-review: PASS, no blockers.

Final doc gate after this evidence append: passed (`git diff --check` and custom doc marker/scope/changed-file/ignored-file/forbidden-boundary/sensitive scan).

## Implementation Approval

Timestamp: 2026-05-06 00:25:22 CST +0800

User approved implementation with:

```text
批准 Phase 5D 实现
```

Approval scope remained the plan boundary: pure helper, focused tests, tiny `gateway/run.py` existing-seam hook, dev log, gates, review, commit, push, PR creation. No live runtime publish, service lifecycle, Gateway restart, production tool registry, platform adapter, config-write, PR merge, or remote branch deletion approval was granted.

## Implementation Summary

Created:

- `gateway/flowweaver_shadow_publisher.py`
- `tests/gateway/test_flowweaver_shadow_publisher.py`
- `tests/gateway/test_flowweaver_shadow_publisher_run_hook.py`

Modified:

- `gateway/run.py`
- this dev log

Implemented behavior:

1. `is_flowweaver_shadow_runtime_publish_enabled()` returns true only when all three task-tracker flags are enabled:
   - `flowweaver_shadow`
   - `flowweaver_shadow_dry_run`
   - `flowweaver_shadow_runtime_publish`
2. `build_flowweaver_shadow_runtime_publication()` derives a safe Phase 5D summary from already-safe shadow/dry-run inputs and the Phase 5A runtime ingress envelope.
3. `build_flowweaver_delivery_ack_updates()` projects Gateway-owned delivery state into synthetic `record_delivery_ack` update request dictionaries only.
4. `attach_flowweaver_shadow_runtime_publication()` mutates `agent_result` only when explicitly enabled and only for a ready summary.
5. `gateway/run.py` now resolves the Phase 5D flag beside the existing FlowWeaver shadow/dry-run config and calls the helper only inside the existing shadow/dry-run seam.
6. Publisher hook exceptions fail closed and log only a stable sanitized debug message: `FlowWeaver shadow runtime publication attach failed`.

Preserved boundaries:

- No live Temporal publish from Gateway.
- No Gateway import of Phase 5C runtime client, MCP, Temporal client, worker, or service code.
- No subprocess/Docker/daemon/service startup.
- No production Hermes tool/global registry/config writes.
- No platform adapter changes.
- No visible IM behavior change; tests verify adapter send/edit counts stay unchanged under Phase 5D shadow publishing.

## TDD Evidence

RED 1 — helper module absent:

```text
scripts/run_tests.sh tests/gateway/test_flowweaver_shadow_publisher.py -q
→ ModuleNotFoundError: No module named 'gateway.flowweaver_shadow_publisher'
```

GREEN 1 — pure helper implemented:

```text
scripts/run_tests.sh tests/gateway/test_flowweaver_shadow_publisher.py -q
→ 10 passed
python -m py_compile gateway/flowweaver_shadow_publisher.py
→ passed
```

RED 2 — run-loop hook absent after valid run-hook tests:

```text
scripts/run_tests.sh tests/gateway/test_flowweaver_shadow_publisher_run_hook.py -q
→ 2 failed, 1 passed
```

The two expected failures were:

- no `flowweaver_shadow_runtime_publication` attached when all three gates were on;
- no sanitized failure-log message because the hook did not exist yet.

GREEN 2 — tiny run-loop hook implemented:

```text
scripts/run_tests.sh tests/gateway/test_flowweaver_shadow_publisher_run_hook.py -q
→ 3 passed
```

Combined focused gate:

```text
scripts/run_tests.sh tests/gateway/test_flowweaver_shadow_publisher.py tests/gateway/test_flowweaver_shadow_publisher_run_hook.py -q
python -m py_compile gateway/run.py gateway/flowweaver_shadow_publisher.py
→ 13 passed; py_compile passed
```

## Regression / Boundary Verification

Focused Phase 5D + prior FlowWeaver regression gate:

```text
scripts/run_tests.sh \
  tests/gateway/test_flowweaver_shadow_publisher.py \
  tests/gateway/test_flowweaver_shadow_dry_run.py \
  tests/gateway/test_flowweaver_runtime_contract.py \
  tests/gateway/test_flowweaver_shadow_publisher_run_hook.py \
  -q
python -m py_compile gateway/flowweaver_shadow_publisher.py gateway/run.py
git diff --check
→ 34 passed; py_compile passed; git diff --check passed
```

Custom scans:

```text
changed_file_allowlist: PASS
forbidden_surface: PASS
diff_hunk_forbidden_runtime_source: PASS
config_write_added_gateway_lines: PASS
secret_scan: PASS
private_id_literal_scan: PASS
```

Changed files observed after implementation:

```text
docs/dev_log/2026-05-05-flowweaver-phase5d-gateway-shadow-publisher-ack-bridge.md
docs/plans/2026-05-05-flowweaver-phase5d-gateway-shadow-publisher-ack-bridge.md
gateway/flowweaver_shadow_publisher.py
gateway/run.py
tests/gateway/test_flowweaver_shadow_publisher.py
tests/gateway/test_flowweaver_shadow_publisher_run_hook.py
```

## Independent Reviews

Plan/spec implementation review:

```text
PASS
```

Reviewer summary:

- changed files are within the approved Phase 5D boundary;
- runtime publication is default-off and requires all three flags;
- no new Gateway Temporal/MCP/runtime-client/service/process imports/calls;
- no platform adapter, production tool registry/toolset, or config-write changes;
- hook is narrow and inside the existing FlowWeaver shadow/dry-run seam;
- ACK bridge emits only synthetic `record_delivery_ack` updates;
- tests cover helper gating, safe summary construction, ACK projection/redaction, hostile inputs, run-hook default-off/opt-in, and sanitized failure logging.

Security / low-intrusion review:

```text
PASS
```

Reviewer summary:

- no live runtime publishing added;
- no forbidden Gateway runtime/client/MCP/service/process additions in diff;
- no config writes, registry changes, or platform adapter changes;
- publisher hook failure logging is stable and sanitized, with no raw exception interpolation;
- summary output is synthetic and does not copy raw delivery IDs, card JSON, platform payloads, or exception text.

## Missed-Test Reflection

1. First run-hook RED attempt had a fixture setup error because one temp config directory was not created before writing `config.yaml`. Fixed the test harness setup, then reran to get meaningful RED failures against the missing hook.
2. One helper test initially over-asserted that the string `card_json` could not appear anywhere in the full summary. That was too broad because the Phase 5A claim-check policy legitimately lists forbidden material names as metadata. Tightened the assertion to the ACK bridge output, which is the actual leak surface being tested.
3. The final gate includes both tests and custom scans because tests prove behavior while scans prove boundary discipline against forbidden surfaces.
