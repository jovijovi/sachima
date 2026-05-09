# Dev Log — FlowWeaver Phase 29 Stub Activity Implementation

## Scope

Approved phase: Phase 29 (P29).

Implementation branch/worktree:

```text
feat/flowweaver-phase29-stub-activity-implementation
/home/ubuntu/workspace/hermes/worktrees/sachima/feat-flowweaver-phase29-stub-activity-implementation
```

## Guardrails

Strongest allowed verdict:

```text
ready_for_local_temporal_stub_activity_orchestration
```

- No Temporal SDK imports.
- No `Client`, `Worker`, `WorkflowEnvironment`, `@activity.defn`, `workflow.execute_activity`, retry objects, timeout SDK objects, or task queues.
- No `@activity.defn` wrappers; P29 functions are plain Python stubs only.
- No call to `build_flowweaver_stub_activity_implementation_validation_report`.
- No call to `build_flowweaver_stub_activity_implementation_design_report`.
- No call to `build_flowweaver_stub_activity_boundary_contract_validation_report`.
- No call to `build_flowweaver_stub_activity_boundary_contract_report`.
- No call to `build_flowweaver_stub_activity_orchestration_validation_report`.
- No call to `orchestrate_flowweaver_stub_activities`.
- No prototype imports.
- No Gateway hook changes.
- No platform adapter mutation/access.
- No production config writes.
- No Gateway restart requirement.
- No real Temporal Activity execution.
- No real agent or tool execution.
- No real delivery ACK updates.
- No real send/edit/render/callback control.
- No file, claim-check storage, subprocess, socket, Docker, daemon, external service, or service startup.
- No logs or prints.
- No raw prompt/message/tool/card/media/platform/private id/callback/credential/raw exception material in outputs, logs, fixtures, reports, docs, or user-visible output.

## RED Evidence

Initial RED command:

```bash
scripts/run_tests.sh tests/gateway/test_flowweaver_stub_activity_implementation.py -q
```

Result:

```text
ModuleNotFoundError: No module named 'gateway.flowweaver_stub_activity_implementation'
```

This proved the new P29 implementation module was absent before implementation.

## GREEN Evidence

Focused P29 test:

```bash
scripts/run_tests.sh tests/gateway/test_flowweaver_stub_activity_implementation.py -q
```

Initial result after implementation:

```text
47 passed in 1.61s
```

After changed-file allowlist maintenance:

```text
47 passed in 1.32s
```

After Codex blocker fix for hostile `__repr__` fail-closed behavior:

```text
48 passed in 1.15s
```

After independent review blocker fix for avoiding arbitrary `__repr__` invocation entirely:

```text
49 passed in 1.16s
```

After blocker-only re-review fix for cyclic plain containers:

```text
50 passed in 1.18s
```

After final blocker-only re-review fix for cyclic Phase 28 builder reports:

```text
51 passed in 1.14s
```

After final Codex review fix for deeply nested acyclic containers:

```text
53 passed in 1.15s
```

## Verification Log

Initial FlowWeaver regression command:

```bash
scripts/run_tests.sh tests/gateway/test_flowweaver_*.py tests/prototypes/test_flowweaver_phase5c_runtime_client_contract.py -q
```

Result:

```text
10 failed, 658 passed in 5.46s
```

All failures were changed-file guard allowlists in prior FlowWeaver phase tests rejecting the seven P29/roadmap files. No behavior assertion failed. The allowlists were updated with only the P29 roadmap docs, P29 plan/dev-log/runbook, P29 module, and P29 test path.

Re-run result before Codex review:

```text
668 passed in 5.11s
```

Final re-run after Codex blocker fix:

```text
669 passed in 4.93s
```

Final re-run after independent review blocker fix:

```text
670 passed in 3.77s
```

Final re-run after blocker-only re-review fix:

```text
671 passed in 4.92s
```

Final re-run after final blocker-only re-review fix:

```text
672 passed in 5.00s
```

Final re-run after final Codex review fix:

```text
674 passed in 5.09s
```

Whitespace / patch hygiene:

```bash
git diff --check
```

Result:

```text
PASS
```

## Review / Safety Gate

Codex read-only blocker review returned:

```text
VERDICT: BLOCK
BLOCKERS:
- gateway/flowweaver_stub_activity_implementation.py called repr(value) before fail-closed handling, so a hostile object with raising __repr__ could propagate a raw RuntimeError instead of returning a sanitized rejected result.
```

Fix applied:

```text
- Added a RED regression with HostileRepr for validate_claim_check_ref, execute_agent_turn, and deliver_artifact.
- Updated _contains_forbidden_material to treat repr failures as unsafe material.
- Re-ran the focused HostileRepr test: 1 passed.
- Re-ran focused P29 suite: 48 passed.
- Re-ran FlowWeaver regression: 669 passed.
```

Pending Codex blocker-only re-review and independent code review.

Codex blocker-only re-review returned:

```text
VERDICT: PASS
BLOCKERS:
- None
```

Independent code review returned:

```text
VERDICT BLOCK
BLOCKERS
- gateway/flowweaver_stub_activity_implementation.py still called repr(value) on arbitrary public stub inputs via _contains_forbidden_material before exact plain-tree validation. A side-effectful __repr__ could execute side effects despite the side-effect-free boundary. Tests covered raising __repr__, but not avoiding __repr__ invocation entirely.
```

Second fix applied:

```text
- Added SideEffectRepr RED regression proving public stubs do not invoke arbitrary __repr__.
- Replaced repr-based unsafe scanning with structural plain-tree scanning over exact dict/list/str/int/bool/None values.
- Treat non-plain objects and hostile keys as unsafe material without calling repr.
- Re-ran the SideEffectRepr focused test: 1 passed.
- Re-ran focused P29 suite: 49 passed.
- Re-ran FlowWeaver regression: 670 passed.
```

Pending independent blocker-only re-review.

Independent blocker-only re-review returned:

```text
VERDICT: BLOCK
BLOCKERS:
- _contains_forbidden_material still did unguarded recursive scanning of exact dict/list inputs. Self-referential plain containers could raise raw RecursionError instead of failing closed with sanitized unsafe_material.
```

Third fix applied:

```text
- Added cyclic plain dict/list RED regression for validate_claim_check_ref, execute_agent_turn, and deliver_artifact.
- Added a seen-set to structural unsafe scanning.
- Treat recursive containers as unsafe material.
- Re-ran the cyclic-container focused test: 1 passed.
- Re-ran focused P29 suite: 50 passed.
- Re-ran FlowWeaver regression: 671 passed.
```

Pending final blocker-only re-review.

Final blocker-only re-review returned:

```text
VERDICT: BLOCK
BLOCKERS:
- build_flowweaver_stub_activity_implementation_report called _assert_plain_tree on implementation_validation_report without cycle detection. A cyclic exact plain dict/list could raise raw RecursionError instead of returning the sanitized Phase 29 error report.
```

Fourth fix applied:

```text
- Added a cyclic Phase 28 report RED regression for the P29 builder.
- Added a seen-set to _assert_plain_tree.
- Treat recursive prior-phase artifacts as invalid sanitized input.
- Re-ran the cyclic builder focused test: 1 passed.
- Re-ran focused P29 suite: 51 passed.
- Re-ran FlowWeaver regression: 672 passed.
```

Pending final review rerun.

Final Codex review returned:

```text
VERDICT: BLOCK
BLOCKERS:
- Recursive _assert_plain_tree / _contains_forbidden_material still failed open for deeply nested acyclic plain containers. Public stubs and the P29 builder could raise raw RecursionError at high depth instead of returning sanitized unsafe_material / invalid Phase 28 report results.
```

Fifth fix applied:

```text
- Added deeply nested acyclic container RED regressions for public stubs and the P29 builder.
- Added _MAX_PLAIN_TREE_DEPTH and depth tracking to _contains_forbidden_material and _assert_plain_tree.
- Treat too-deep plain trees as unsafe/invalid sanitized input before Python recursion limits.
- Re-ran the deeply nested focused tests: 2 passed.
- Re-ran focused P29 suite: 53 passed.
- Re-ran FlowWeaver regression: 674 passed.
```

Pending final Codex and independent review reruns.

Final Codex review rerun returned:

```text
VERDICT: PASS
BLOCKERS:
- None
```

Final independent review rerun returned:

```text
VERDICT: PASS
BLOCKERS: None.
```

Final review notes confirmed:

```text
- Changed paths are limited to P29 module/test/docs/roadmap plus exact allowlist additions.
- No Temporal SDK, Gateway runtime/adapter, production config, restart, delivery/ACK, agent/tool execution, or side-effect calls found.
- Builder consumes Phase 28 descriptor/report via descriptor + validator only; no prior builders/orchestrators are called.
- Fail-closed handling covers hostile/non-plain/cyclic/deep inputs without repr invocation or raw echo.
```

Final post-review evidence append gate:

```text
git diff --check: PASS
added-line static security scan: no output
scripts/run_tests.sh tests/gateway/test_flowweaver_stub_activity_implementation.py -q: 53 passed in 1.16s
scripts/run_tests.sh tests/gateway/test_flowweaver_*.py tests/prototypes/test_flowweaver_phase5c_runtime_client_contract.py -q: 674 passed in 5.05s
```
