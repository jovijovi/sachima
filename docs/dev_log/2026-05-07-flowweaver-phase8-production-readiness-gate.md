# FlowWeaver Phase 8 — Production Readiness Gate / Controlled Gateway Boundary Dev Log

## Task Background

狗哥 asked to start Phase 8 design on 2026-05-07 after Phase 7 PR #39 was verified merged and the local canonical repo was synchronized.

Current merged context:

```text
Phase 5: Durable Runtime Foundation through 5K — merged
Phase 6: Gateway ACK Shadow Bridge — merged
Phase 7: Gateway Shadow E2E Loop — merged
Current base: origin/feature/sachima-channel @ a5b68a43b4a8f5297077eeff7b5268ec149578d7
```

Phase 8 target:

```text
Design a default-off production-readiness gate that evaluates sanitized Phase 7 loop output plus caller-supplied boundary descriptors, then emits a safe go/no-go report for a future controlled Gateway integration design. It must not enable production Gateway wiring or real IM side effects.
```

This phase remains design-first, prototype-only, local-only, default-off, and production-zero until 狗哥 explicitly approves implementation.

## Problems Encountered

- The Sachima repo does not have `AI_FLOW.md`; the design follows `AGENTS.md` plus the established `docs/plans/` and `docs/dev_log/` pattern used by Phases 4–7.
- Phase 7 is now merged, so Phase 8 must avoid restating Phase 7 as future work.
- The tempting next step is production Gateway wiring, but that is still too risky without a readiness gate and explicit production approval boundaries.
- `scripts/run_tests.sh` intentionally ignores `tests/integration/**`; any future integration regression must use direct hermetic pytest commands.

## Root Cause Analysis

Phase 7 proved a shadow E2E loop, but it did not define the contract for deciding whether production wiring is even safe to design. Without a separate readiness gate, future work could accidentally mix three concerns:

```text
1. validating safe durable/runtime state,
2. designing controlled Gateway integration boundaries,
3. actually enabling production side effects.
```

Those concerns must stay separated. Phase 8 should produce a safe readiness report and a candidate contract only; actual production activation requires separate future approval.

## Solution

Plan saved:

```text
docs/plans/2026-05-07-flowweaver-phase8-production-readiness-gate.md
```

Proposed design summary:

```text
Add a pure prototype-only readiness evaluator:
Phase 7 result + gateway boundary descriptor + runtime boundary descriptor + operational policy
  -> safe readiness report
  -> candidate contract for a future controlled-shadow design
  -> explicit separate-approval checklist
```

Hard boundaries:

```text
No production Gateway/Feishu/Sachima integration.
No gateway/run.py or gateway/platforms/** behavior changes.
No run_agent.py, model_tools.py, toolsets.py, tools/**, hermes_cli/** changes.
No production tool registration, Gateway restart, Docker/daemon/service startup, global registry/config writes, or external simulator repo changes.
No Temporal client/Worker construction inside the Phase 8 module.
No payload-carrying Temporal Signals.
All production actions require separate approval.
No raw platform/card/media/prompt/tool output/secret material in inputs, reports, fixtures, logs, or docs evidence.
```

## Alternatives Considered

- Direct production Gateway integration: rejected. Phase 7 proves shadow readiness, not production activation safety.
- External `sachima-im-simulator` changes in this phase: rejected. That is a separate repo and should get its own plan/branch/PR if needed.
- Making Phase 8 start a local Temporal worker or Gateway smoke harness: rejected for this readiness module. Existing integration regressions may still run as gates, but the Phase 8 module itself should be pure and lifecycle-free.
- Returning `production_ready` / `production_enabled`: rejected. The report should say only `ready_for_controlled_shadow_design`, which is weaker and safer.

## Verification

Baseline repo/worktree state:

```text
canonical repo: /home/ubuntu/workspace/hermes/repo/sachima
Phase 8 worktree: /home/ubuntu/workspace/hermes/worktrees/sachima/feat-flowweaver-phase8-production-readiness-gate
Phase 8 branch: feat/flowweaver-phase8-production-readiness-gate
Base HEAD: a5b68a43b4a8f5297077eeff7b5268ec149578d7
```

Design-gate verification current status:

```text
1. Relevant skills loaded: plan, writing-plans, Temporal durable orchestration, native IM channel, local runtime reconciliation, Gateway simulator loop verification, GitHub PR workflow, workspace worktree discipline.
2. Past-session context searched for Sachima Phase 8 / production readiness / Gateway Shadow E2E.
3. Current Phase 7 plan/dev log and implementation surfaces inspected.
4. Phase 8 isolated worktree created.
5. Phase 8 plan/dev log drafted.
6. Document gate and custom changed-file / forbidden-surface / secret-shaped scan: PASS after tightening exact marker wording.
7. Codex fresh-context design review: PASS, blockers none.
8. Codex non-blocking note accepted: `start_status` must mirror actual Phase 7 behavior (`started` / `running`) and must not include `duplicate`; plan patched accordingly.
9. Pending: final document gate after this evidence append.
```

## Implementation Progress

2026-05-07 — 狗哥 approved Phase 8 implementation after the design gate.

Implemented files:

```text
prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/production_readiness_gate.py
tests/prototypes/test_flowweaver_phase8_production_readiness_gate.py
docs/runbooks/flowweaver-production-readiness.md
```

Implementation summary:

```text
safe Phase 7 result + strict Gateway/runtime/operational descriptors -> readiness report
```

The Phase 8 module is synchronous and pure. It imports no Gateway/platform/tool/config/runtime service lifecycle surfaces and does not import Temporal client/worker/workflow modules.

## TDD Notes

```text
1. RED: scripts/run_tests.sh tests/prototypes/test_flowweaver_phase8_production_readiness_gate.py -q
   -> 7 failed with ModuleNotFoundError for flowweaver_runtime_client.production_readiness_gate.
2. GREEN first attempt: implementation added but 4 tests failed because the unsafe-material scanner treated safe descriptor policy field names as leaks.
3. Fix: allow descriptor policy field names only at the descriptor top level while still scanning their values and rejecting unsafe extra keys/values.
4. GREEN: scripts/run_tests.sh tests/prototypes/test_flowweaver_phase8_production_readiness_gate.py -q
   -> 7 passed.
5. Integration guard RED: direct integration pytest failed because Phase 5H/I/J/K changed-file allowlists did not know Phase 8 files.
6. Fix: append only Phase 8 plan/dev log/runbook/module/test paths to those guard allowlists; no forbidden production path was added.
7. Codex implementation review found blockers:
   - nested Phase 7 raw material / private snapshot identifiers could bypass the sanitizer;
   - malformed Gateway descriptor values could raise TypeError instead of returning a stable blocked report.
8. RED: added focused regressions for nested raw material, nested private snapshot IDs, and malformed descriptor values.
9. GREEN: fixed Phase 7 input scanning, private-prefix key rejection, and Gateway descriptor type checks.
10. Codex blocker re-check found one remaining blocker: policy-name-only nested raw material was not proven rejected.
11. RED: added policy-name-only nested `forbidden_material`, `runbook_outline`, and raw-card value cases.
12. GREEN: exact input keys `forbidden_material` / `runbook_outline` and raw-material value markers now fail closed as `unsafe_material`.
```

## Final Verification

```text
Focused Phase 8:
- scripts/run_tests.sh tests/prototypes/test_flowweaver_phase8_production_readiness_gate.py -q
- 9 passed

Prototype regression:
- Phase 8 + Phase 7/6/5K/5J/5I/5G/5F/5E/5C/5B prototype suite
- 127 passed

Integration regression:
- Direct pytest, not scripts/run_tests.sh, for Phase 7/6/5K/5J/5I/5H/5C/5B integration suite
- 38 passed

Static gates:
- python -m py_compile: PASS
- python -m ruff check: PASS
- git diff --check: PASS
- changed-file allowlist / forbidden path / forbidden import-call-marker / added-line secret-shaped scan: PASS

Codex review:
- Implementation review: BLOCK on sanitizer / malformed descriptor handling.
- Blocker re-check #1: BLOCK on policy-name-only nested raw material.
- Blocker re-check #2: PASS, blockers none.
```

## Follow-up Notes

- Phase 8 still must not be treated as production activation.
- Any future controlled Gateway design requires separate approval.
- This implementation remains default-off, prototype-only, lifecycle-free, and side-effect-free.
