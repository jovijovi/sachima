# FlowWeaver Phase 7 — Gateway Shadow E2E Loop / IM Simulator Harness Dev Log

## Task Background

狗哥 approved moving into Phase 7 on 2026-05-07 and allowed Codex when useful. The collaboration rule for this phase is explicit: Codex may act as temporary system architect/reviewer/coder only after Hermes provides enough context and concrete deliverables, and Hermes remains responsible for verification.

Phase 7 target:

```text
Build a prototype-only/default-off shadow E2E loop that starts/queries runtime, builds a sanitized simulated Gateway publication envelope, routes simulated delivery ACKs through the Phase 6 ACK bridge, and verifies final runtime snapshot parity without touching production Gateway or real Feishu.
```

This phase remains shadow/simulator-only, local/prototype-only, default-off, and production-zero.

## Problems Encountered

- The canonical Sachima repo has no existing Phase 7 plan, so this phase starts from a fresh design gate.
- The separate `sachima-im-simulator` repo exists and has useful simulator context, but its main checkout currently has unrelated local doc changes. Phase 7 should not mix cross-repo simulator changes into this Sachima PR.
- `scripts/run_tests.sh` still intentionally ignores `tests/integration/**`, so integration gates must use direct hermetic pytest commands. Using the wrapper for integration would be a false-clean/no-test trap.

## Root Cause Analysis

Phase 6 proved a narrow ACK-to-runtime reconciliation seam, but it did not prove the whole shadow delivery loop. Production Gateway integration would still be premature because a full loop must show that publication surfaces, simulated Gateway delivery, ACK reconciliation, final snapshot parity, and no-leak constraints all hold together.

## Solution

Plan saved:

```text
docs/plans/2026-05-07-flowweaver-phase7-gateway-shadow-e2e-loop.md
```

Proposed design summary:

```text
Add a prototype-only runtime-client E2E harness:
publication summary -> start_transaction -> query_transaction -> sanitized shadow publication envelope -> simulated delivery ACK envelopes -> Phase 6 bridge -> final query_transaction.
```

Hard boundaries:

```text
No production Gateway/Feishu integration.
No gateway/run.py or gateway/platforms/** changes.
No run_agent.py, model_tools.py, toolsets.py, tools/**, hermes_cli/** changes.
No production tool registration, Gateway restart, Docker/daemon/service startup, global registry/config writes, or external simulator repo changes.
No raw platform/card/media/prompt/tool output/secret material in runtime history or returned artifacts.
```

## Alternatives Considered

- Direct Production Gateway Integration: rejected for now. Phase 6 only proved ACK bridge safety, not the full publication -> simulated delivery -> ACK -> snapshot loop.
- Modify `sachima-im-simulator` in the same phase: rejected for this Sachima PR because it is a separate private repo with unrelated local changes. If needed later, use a separate simulator repo plan/branch/PR.
- Reuse `publish_shadow_runtime_publication()` direct ACK path as the Phase 7 proof: rejected because it bypasses the Phase 6 bridge. Phase 7 specifically needs to prove ACKs go through the same shadow bridge that future Gateway integration would use.

## Verification

Baseline repo/worktree state:

```text
canonical repo: /home/ubuntu/workspace/hermes/repo/sachima
canonical branch: feature/sachima-channel
canonical HEAD: 654b4bafd79da394dc6f23ce5ce430b733c90533
origin/feature/sachima-channel: 654b4bafd79da394dc6f23ce5ce430b733c90533
Phase 7 branch: feat/flowweaver-phase7-gateway-shadow-e2e-loop
Phase 7 worktree: /home/ubuntu/workspace/hermes/worktrees/sachima/feat-flowweaver-phase7-gateway-shadow-e2e-loop
```

Fresh baseline gates before Phase 7 changes:

```text
scripts/run_tests.sh [Phase 5/6 prototype regression] -q
-> 110 passed in 0.79s

TZ=UTC LANG=C.UTF-8 LC_ALL=C.UTF-8 PYTHONHASHSEED=0 /home/ubuntu/.hermes/hermes-agent/venv/bin/python -m pytest -o addopts= -n 4 [Phase 5/6 integration regression] -q
-> 36 passed in 1.70s
```

Design-gate verification current status:

```text
1. Document gate for Phase 7 plan/dev log: PASS.
2. Codex fresh-context system-architecture review: initial BLOCK.
   - Blocker 1: entrypoint was not explicitly async even though control_surface.handle() and Phase 6 reconcile_shadow_gateway_ack() are async.
   - Blocker 2: integration proof could be misread as pre-starting the workflow before the Phase 7 entrypoint, which would only prove duplicate-start behavior.
3. Plan patched:
   - `run_shadow_gateway_e2e_loop` is now explicitly `async def`.
   - Module must not own the event loop: no `asyncio.run`, loop creation, background tasks, task groups, or hidden lifecycle.
   - Entry point must perform bounded readiness query/poll itself.
   - Integration RED test must call the entrypoint against a fresh unstarted local Temporal workflow and prove the entrypoint performs start -> query/poll -> Phase 6 ACK bridge -> final query.
4. Post-patch document gate: PASS.
5. Codex blocker-only re-review: PASS, blockers none.
6. Ask 狗哥 for design approval before behavior-bearing code.
```

## Implementation Progress

2026-05-07 12:12:58 CST +0800 — Phase 7 behavior implementation completed in the isolated worktree.

Implemented files:

```text
prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/gateway_shadow_e2e_loop.py
tests/prototypes/test_flowweaver_phase7_gateway_shadow_e2e_loop.py
tests/integration/test_flowweaver_phase7_gateway_shadow_e2e_loop.py
```

Guard-only allowlist updates:

```text
tests/integration/test_flowweaver_phase5h_local_temporal_worker_reconciliation.py
tests/integration/test_flowweaver_phase5i_start_signature_parity.py
tests/integration/test_flowweaver_phase5j_activity_claim_check_boundary.py
tests/integration/test_flowweaver_phase5k_runtime_control_surface.py
```

Implementation summary:

```text
safe ready publication -> validate start/runtime_identity/checks/ACK plan -> start_transaction -> bounded query_transaction -> sanitized Phase 7 publication envelope -> Phase 6 reconcile_shadow_gateway_ack() per simulated ACK -> final query_transaction
```

The Phase 7 module remains prototype-only/default-off and caller-supplied-client only. It imports no production Gateway/platform/tool/config/service lifecycle surfaces and does not import Temporal client/worker/workflow modules.

## TDD / Review Notes

TDD checkpoints:

```text
1. Import/API RED: ModuleNotFoundError for missing gateway_shadow_e2e_loop module.
2. Happy-path RED: stub did not call start/query/Phase 6 bridge/final query.
3. Replay harness issue: initial fake reset snapshot on duplicate start; fixed the test harness so duplicate start emulates real runtime behavior before counting it as valid evidence.
4. Codex blocker RED: stale runtime_identity / false checks were accepted and reached runtime; added focused regression and verified it failed before implementation.
```

Codex implementation review:

```text
Initial implementation review: BLOCK
- Missing runtime_identity/checks validation.
- Phase 7 fixtures used stale identity type/strategy.

Fix:
- Added exact runtime_identity validation for flowweaver.gateway.runtime_identity.v0 / shadow_ref_hash_v0.
- Added exact checks validation requiring all Phase 5D/5G checks to be True.
- Updated prototype/integration fixtures to the actual publisher identity shape.

Blocker-only re-review: BLOCK
- Phase 5I runtime_scanned_paths was accidentally weakened during allowlist cleanup.

Fix:
- Restored Phase 5I runtime_scanned_paths from origin/feature/sachima-channel.
- Restored Phase 5H/5I/5J/5K allowlist blocks from base and only appended Phase 7 files.

Final Codex blocker-only re-review: PASS, blockers none.
```

## Implementation Verification

Fresh post-implementation verification:

```text
scripts/run_tests.sh tests/prototypes/test_flowweaver_phase7_gateway_shadow_e2e_loop.py -q
-> 8 passed in 0.39s

TZ=UTC LANG=C.UTF-8 LC_ALL=C.UTF-8 PYTHONHASHSEED=0 /home/ubuntu/.hermes/hermes-agent/venv/bin/python -m pytest -o addopts= -n 4 tests/integration/test_flowweaver_phase7_gateway_shadow_e2e_loop.py -q
-> 2 passed in 0.80s

scripts/run_tests.sh [Phase 7 + Phase 6 + Phase 5K..5B prototype regression] -q
-> 118 passed in 0.71s

TZ=UTC LANG=C.UTF-8 LC_ALL=C.UTF-8 PYTHONHASHSEED=0 /home/ubuntu/.hermes/hermes-agent/venv/bin/python -m pytest -o addopts= -n 4 [Phase 7 + Phase 6 + Phase 5K/5J/5I/5H/5C/5B integration regression] -q
-> 38 passed in 1.83s

python -m py_compile [Phase 7 module/tests + touched allowlist tests]
python -m ruff check [Phase 7 module/tests + touched allowlist tests]
git diff --check
-> PASS

Custom changed-file / forbidden-surface / secret scan
-> PASS
```

## Follow-up Notes

Loaded and applied relevant workflow skills: worktree discipline, writing plans, strict TDD, Codex usage, low-intrusion prototype landing, local runtime reconciliation validation, Gateway simulator loop verification, and verification-before-completion.

Skill guidance was validated against live repo facts:

- `scripts/run_tests.sh` was read and confirmed to ignore integration tests.
- Phase 6 plan/dev log and implementation were inspected.
- Phase 5F/5G publication and reconciliation helpers were inspected.
- The separate IM simulator repo was inspected as context only and will not be modified in this Sachima PR.
